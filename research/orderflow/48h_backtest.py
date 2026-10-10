"""TerraQuant Orderflow V2 — 48-hour BTC/SOL research, no wallet, no orders."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import io,json,time,requests,numpy as np,pandas as pd

OUTPUT=Path("research/orderflow")
OUTPUT.mkdir(parents=True,exist_ok=True)
START=datetime(2026,9,2,tzinfo=timezone.utc)
HOURS=48
SYMBOLS=("BTC","SOL")
HOLDS=(30,60,120)
ROUNDTRIP_TAKER_BPS=9.0
ADVERSE_BPS=2.0
session=requests.Session()
def download(path):
    last=None
    for attempt in range(4):
        try:
            response=session.get("https://api.cryptohftdata.com/download",params={"file":path},timeout=60)
            if response.status_code==429 or response.status_code>=500:
                time.sleep(10+attempt*10)
                last=f"HTTP {response.status_code}";continue
            response.raise_for_status()
            if not response.content.startswith(b"PAR1"):
                raise ValueError(f"not Parquet: {path}")
            return response.content
        except Exception as e:
            last=str(e)
            if attempt<3:time.sleep(3+attempt*4)
    raise RuntimeError(f"{path}: {last}")

def coin_research(symbol):
    raw_trades=[];raw_books=[]
    manifest=[];failures=[]
    for h in range(HOURS):
        d=START+timedelta(hours=h)
        for kind in ("trades","orderbook"):
            path=f"hyperliquid_futures/{d:%Y-%m-%d}/{d:%H}/{symbol}_{kind}.parquet"
            try:
                blob=download(path)
                cols=(["received_time","trade_id","trade_time","price","quantity","is_buyer_maker"] if kind=="trades" else ["received_time","side","price","quantity","event_type"])
                df=pd.read_parquet(io.BytesIO(blob),columns=cols)
                (raw_trades if kind=="trades" else raw_books).append(df)
                manifest.append({"path":path,"rows":len(df),"compressed_bytes":len(blob)})
            except Exception as e:
                print("DOWNLOAD_FAILED",path,str(e),flush=True)
                failures.append({"path":path,"error":str(e)})
        if h%6==5:print("PROGRESS",symbol,h+1,"/",HOURS,"hours",flush=True)
        time.sleep(0.35) # Well below free tier 60 requests/min over sustained hours.
    if failures:raise RuntimeError(f"{symbol} missing historical hour files: {str(failures[:10])}")
    tr=pd.concat(raw_trades,ignore_index=True)
    ob=pd.concat(raw_books,ignore_index=True)
    tr=tr.drop_duplicates(["trade_id","trade_time"]).sort_values("received_time")
    tr["received_time"]=pd.to_numeric(tr.received_time)
    tr["value"]=pd.to_numeric(tr.price)*pd.to_numeric(tr.quantity)
    tr["aggressor_buy"]=~tr["is_buyer_maker"].astype(str).str.lower().isin(["true","1"])
    tr["seconds"]=(tr.received_time//10**9).astype("int64")
    tr["buy_usd"]=np.where(tr.aggressor_buy,tr.value,0.)
    tr["sell_usd"]=np.where(~tr.aggressor_buy,tr.value,0.)
    fs=tr.groupby("seconds",sort=True)[["buy_usd","sell_usd"]].sum()
    secs=fs.index.to_numpy(dtype="int64")
    buy_prefix=np.r_[0,np.cumsum(fs.buy_usd.to_numpy())]
    sell_prefix=np.r_[0,np.cumsum(fs.sell_usd.to_numpy())]
    ob=ob.loc[(ob.event_type=="snapshot") & (pd.to_numeric(ob.quantity)>0)].copy()
    ob["price"]=pd.to_numeric(ob.price)
    ob["quantity"]=pd.to_numeric(ob.quantity)
    bids=ob.loc[ob.side=="bid"].groupby("received_time",sort=True).agg(bid=("price","max"),bid_depth=("quantity","sum"))
    asks=ob.loc[ob.side=="ask"].groupby("received_time",sort=True).agg(ask=("price","min"),ask_depth=("quantity","sum"))
    book=bids.join(asks,how="inner").dropna().reset_index().sort_values("received_time").reset_index(drop=True)
    book=book.loc[(book.bid>0)&(book.ask>=book.bid)].reset_index(drop=True)
    t=book.received_time.to_numpy(dtype="int64")
    bid=book.bid.to_numpy()
    ask=book.ask.to_numpy()
    mid=(bid+ask)/2
    q=t//10**9
    starts=np.searchsorted(secs,q-30,side="left")
    ends=np.searchsorted(secs,q,side="left")
    bv=buy_prefix[ends]-buy_prefix[starts]
    sv=sell_prefix[ends]-sell_prefix[starts]
    ofi=np.divide(bv-sv,bv+sv,out=np.zeros_like(bv),where=bv+sv>0)
    biddepth=book.bid_depth.to_numpy()
    askdepth=book.ask_depth.to_numpy()
    obi=np.divide(biddepth-askdepth,biddepth+askdepth,out=np.zeros_like(biddepth),where=biddepth+askdepth>0)
    past=np.searchsorted(t,t-30_000_000_000,side="right")-1
    ret=np.full(len(book),np.nan)
    v=(past>=0)&((t-t[np.maximum(past,0)])<=45_000_000_000)
    ret[v]=10000*(mid[v]/mid[past[v]]-1)
    spread=(ask/bid-1)*10000
    valid=np.isfinite(ret)&(spread<=5)
    dirs={
      "flow_momentum":np.where((ofi>.5)&(ret>3),1,np.where((ofi<-.5)&(ret<-3),-1,0)),
      "flow_exhaustion":np.where((ofi<-.65)&(ret>-2),1,np.where((ofi>.65)&(ret<2),-1,0)),
      "book_imbalance":np.where(obi>.35,1,np.where(obi<-.35,-1,0)),
      "sweep_reversion":np.where((ret<-12)&(ofi<-.60)&(obi>.25),1,np.where((ret>12)&(ofi>.60)&(obi<-.25),-1,0)),
      "price_momentum":np.where(ret>5,1,np.where(ret<-5,-1,0)),
      "price_reversion":np.where(ret>5,-1,np.where(ret<-5,1,0)),
    }
    split=int((START+timedelta(hours=24)).timestamp()*1e9)
    final_time=int((START+timedelta(hours=48)).timestamp()*1e9)
    entries=[]
    results=[]
    for name,dvec in dirs.items():
        dvec=np.where(valid,dvec,0)
        for hold in HOLDS:
            rows=[]
            last_exit=-10**20
            for i in np.flatnonzero(dvec):
                if t[i]<=last_exit+30_000_000_000:continue
                # Require a full 3-second signal-to-order decision lag and fresh later snapshot
                ei=np.searchsorted(t,t[i]+3_000_000_000,side="left")
                if ei>=len(t) or t[ei]-t[i]>12_000_000_000:continue
                xi=np.searchsorted(t,t[ei]+hold*1_000_000_000,side="left")
                if xi>=len(t) or t[xi]-t[ei]-hold*1_000_000_000>12_000_000_000:continue
                if (t[i]<split<=t[xi]) or t[xi]>=final_time:continue
                direction=int(dvec[i])
                entry=ask[ei] if direction==1 else bid[ei]
                exit_=bid[xi] if direction==1 else ask[xi]
                gross=direction*(exit_/entry-1)*10000
                net=gross-ROUNDTRIP_TAKER_BPS-ADVERSE_BPS
                rows.append((int(t[i]),float(gross),float(net)))
                last_exit=t[xi]
            train=[row for row in rows if row[0]<split]
            test=[row for row in rows if row[0]>=split]
            def mean(a,col):return round(float(np.mean([z[col] for z in a])),3) if a else None
            results.append({"symbol":symbol,"strategy":name,"hold_s":hold,"train_n":len(train),"test_n":len(test),
                "train_mean_net_bps":mean(train,2),"test_mean_gross_bps":mean(test,1),
                "test_mean_net_bps":mean(test,2),
                "test_win_pct":round(100*sum(z[2]>0 for z in test)/len(test),2) if test else None,
                "test_total_net_bps":round(sum(z[2] for z in test),2)})
    return {"coin":symbol,"manifest":{"files":len(manifest),"bytes":sum(x["compressed_bytes"] for x in manifest),"historical_trades":len(tr),"orderbook_level_rows":len(ob),"snapshots":len(book),"median_snapshot_interval_seconds":round(float(np.median(np.diff(t))/1e9),3)},"results":results}

if __name__=="__main__":
    report={"study":"TerraQuant Hyperliquid 48-hour multi-market genuine historical screen",
    "period":"2026-09-02 00:00Z through 2026-09-04 00:00Z",
    "train_period":"2026-09-02 (24h)", "holdout_period":"2026-09-03 (24h)",
    "cost_model":"long ask-to-bid or short bid-to-ask, taker fees 9bp roundtrip + extra adverse 2bp roundtrip",
    "latency":">=3 seconds delay; reject if book entry/exit snapshot >12s late","no_live_orders":True,
    "data_source":"CryptoHFTData public Hyperliquid per-hour trades and L2 snapshots",
    "note":"Pilot screening only. 48 hours/2 markets cannot establish persistent alpha, especially with snapshot rather than full event-by-event fills",
    "coin_results":[]}
    for symbol in SYMBOLS:
        report["coin_results"].append(coin_research(symbol))
        print("COMPLETE",symbol,flush=True)
    path=OUTPUT/"48h-backtest.json"
    path.write_text(json.dumps(report,indent=2))
    md=["# Hyperliquid 48-hour real historical orderflow backtest", "", "Data: 2026-09-02 (training) and 2026-09-03 (holdout), BTC + SOL.", "",
        "Bid/ask crossing + 9bps round-trip fees + 2bps adverse execution assumption; 3-second minimum decision lag.","","**Interpretation:** Two days are insufficient to establish long-run profitability. No real orders were placed.",""]
    for c in report["coin_results"]:
        s=c["manifest"]
        md.extend([f"## {c['coin']} — {s['historical_trades']:,} trades, {s['snapshots']:,} book snapshots","",
            "| Strategy | Hold | Train trades | Test trades | Test gross bps/trade | Test net bps/trade | Test win % |",
            "|---|---:|---:|---:|---:|---:|---:|"])
        for x in c["results"]:md.append(f"| {x['strategy']} | {x['hold_s']}s | {x['train_n']} | {x['test_n']} | {x['test_mean_gross_bps']} | {x['test_mean_net_bps']} | {x['test_win_pct']} |")
        md.append("")
    (OUTPUT/"48h-backtest.md").write_text("\n".join(md))
    print("REPORT_COMPLETE",path,flush=True)
