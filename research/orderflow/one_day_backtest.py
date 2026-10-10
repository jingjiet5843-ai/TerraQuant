"""One-day pre-registered screening backtest on genuine Hyperliquid BTC samples.
Not validated alpha: only one trading day and L2 snapshots ~5 seconds apart.
"""
import json, requests, io, pandas as pd, numpy as np, datetime
from pathlib import Path

DAY="2026-09-02"; COIN="BTC"
ROOT=Path("research/orderflow"); ROOT.mkdir(parents=True,exist_ok=True)
def load_all(which):
    chunks=[];total=0
    session=requests.Session()
    import time
    for hour in range(24):
        name=f"hyperliquid_futures/{DAY}/{hour:02d}/{COIN}_{which}.parquet"
        url="https://api.cryptohftdata.com/v1/download"
        for attempt in range(3):
            r=session.get(url,params={"file":name},timeout=100)
            if r.status_code==429:
                time.sleep(int(r.headers.get("Retry-After","60"))+2)
                continue
            r.raise_for_status()
            break
        else:raise RuntimeError("rate limit after retries: "+name)
        chunks.append(pd.read_parquet(io.BytesIO(r.content)))
        total+=len(r.content)
        print("GOT",which,hour,len(chunks[-1]),"size",len(r.content),flush=True)
        time.sleep(1.3)  # anonymous tier <=60 requests per minute
    return pd.concat(chunks,ignore_index=True),total
tr,trade_bytes=load_all("trades");ob,book_bytes=load_all("orderbook")
tr=tr.sort_values(["received_time","trade_id"]).drop_duplicates("trade_id").reset_index(drop=True)
tr["price"]=pd.to_numeric(tr["price"])
tr["quantity"]=pd.to_numeric(tr["quantity"])
tr["aggressor_buy"]=~tr["is_buyer_maker"].astype(str).str.lower().isin(["true","1"])
tr["notional"]=tr["price"]*tr["quantity"]
ob["price"]=pd.to_numeric(ob["price"])
ob["quantity"]=pd.to_numeric(ob["quantity"])
bids=ob.loc[ob["side"]=="bid"].groupby("received_time").agg(bid=("price","max"),bid_depth=("quantity","sum"))
asks=ob.loc[ob["side"]=="ask"].groupby("received_time").agg(ask=("price","min"),ask_depth=("quantity","sum"))
bk=bids.join(asks,how="inner").dropna().reset_index().sort_values("received_time").reset_index(drop=True)
bk=bk.loc[(bk.bid>0)&(bk.ask>=bk.bid)].reset_index(drop=True)
bk["mid"]=(bk.bid+bk.ask)/2
bk["spread_bps"]=10000*(bk.ask/bk.bid-1)
times=bk.received_time.to_numpy(dtype="int64")
tt=tr.received_time.to_numpy(dtype="int64")
buyn=tr.notional.to_numpy()*tr.aggressor_buy.to_numpy()
selln=tr.notional.to_numpy()*(~tr.aggressor_buy.to_numpy())
buy_cum=np.r_[0,buyn.cumsum()]; sell_cum=np.r_[0,selln.cumsum()]
now=np.searchsorted(tt,times,side="left")
start=np.searchsorted(tt,times-30_000_000_000,side="left")
buy=buy_cum[now]-buy_cum[start]; sell=sell_cum[now]-sell_cum[start]
bk["flow_imb"]=np.divide(buy-sell,buy+sell,out=np.zeros_like(buy,dtype=float),where=(buy+sell)>0)
bk["book_imb"]=(bk.bid_depth-bk.ask_depth)/(bk.bid_depth+bk.ask_depth)
lookback=np.searchsorted(times,times-30_000_000_000,side="right")-1
bk["ret30_bps"]=np.where(lookback>=0,10000*(bk.mid.to_numpy()/bk.mid.to_numpy()[np.maximum(0,lookback)]-1),np.nan)
last=times[-1]; cutoff=times[0]+round((last-times[0])*0.70)
results=[]
for name in ("flow_momentum","flow_exhaustion","book_imbalance","sweep_reversion","price_momentum","price_reversion"):
  for hold in (30,60,120):
    t_last_exit=-1
    trade_rows=[]
    for i,row in bk.iterrows():
      r=float(row.ret30_bps); f=float(row.flow_imb); obi=float(row.book_imb)
      if not np.isfinite(r) or row.spread_bps>5:continue
      d=0
      if name=="flow_momentum":d=1 if f>.50 and r>3 else -1 if f<-.50 and r< -3 else 0
      elif name=="flow_exhaustion":d=1 if f<-.65 and r> -2 else -1 if f>.65 and r<2 else 0
      elif name=="book_imbalance":d=1 if obi>.35 else -1 if obi<-.35 else 0
      elif name=="sweep_reversion":d=1 if r< -12 and f<-.60 and obi>.25 else -1 if r>12 and f>.60 and obi<-.25 else 0
      elif name=="price_momentum":d=1 if r>5 else -1 if r< -5 else 0
      elif name=="price_reversion":d=-1 if r>5 else 1 if r< -5 else 0
      if not d or times[i]<=t_last_exit+30_000_000_000:continue
      entry_idx=np.searchsorted(times,times[i]+3_000_000_000,side="left")
      if entry_idx>=len(bk) or times[entry_idx]-times[i]>12_000_000_000:continue
      exit_idx=np.searchsorted(times,times[entry_idx]+hold*1_000_000_000,side="left")
      if exit_idx>=len(bk) or times[exit_idx]-times[entry_idx]-hold*1_000_000_000>12_000_000_000:continue
      ep=float(bk.ask[entry_idx] if d>0 else bk.bid[entry_idx])
      xp=float(bk.bid[exit_idx] if d>0 else bk.ask[exit_idx])
      gross=d*(xp/ep-1)*10000
      net=gross-9-2  # 4.5 bps taker fee each way and 1bps adverse per side; crossing already via bid/ask
      if times[i]<cutoff<times[exit_idx]:continue
      trade_rows.append(dict(t=int(times[i]),gross=gross,net=net,side=d))
      t_last_exit=times[exit_idx]
    train=[x for x in trade_rows if x["t"]<cutoff]
    test=[x for x in trade_rows if x["t"]>=cutoff]
    def average(rows,key):return round(float(np.mean([x[key] for x in rows])),4) if rows else None
    results.append(dict(strategy=name,hold_seconds=hold,train_trades=len(train),test_trades=len(test),train_mean_net_bps=average(train,"net"),test_mean_gross_bps=average(test,"gross"),test_mean_net_bps=average(test,"net"),test_win_rate=round(sum(x["net"]>0 for x in test)/len(test),4) if test else None,test_total_net_bps=round(sum(x["net"] for x in test),3)))
diffs=np.diff(times)/1e9
report={
 "sample":{"source":"CryptoHFTData anonymous full-day download: Hyperliquid Futures BTC 2026-09-02","coin":"BTC","first_time":datetime.datetime.fromtimestamp(times[0]/1e9,datetime.timezone.utc).isoformat(),"last_time":datetime.datetime.fromtimestamp(times[-1]/1e9,datetime.timezone.utc).isoformat(),"trade_rows":len(tr),"book_rows":len(ob),"book_snapshots":len(bk),"median_snapshot_spacing_s":round(float(np.median(diffs)),3),"max_snapshot_spacing_s":round(float(np.max(diffs)),3),"sample_trade_bytes":trade_bytes,"sample_orderbook_bytes":book_bytes},
 "protocol":{"split":"first 70% of clock time train, last 30% test; exclude boundary-crossing trades","signal_information":"last 30 seconds of trade notional and book depth; strictly prior received timestamps","entry":"earliest book snapshot at least 3s after signal, reject if over 12s stale","exit":"first book snapshot at least hold_seconds after entry, reject if over 12s stale","prices":"long entry ask / exit bid; short entry bid / exit ask","taker_fee_roundtrip_bps":9,"additional_adverse_roundtrip_bps":2,"funding":"omitted on <=120s horizons","simultaneous_exposure":"no overlapping trades per strategy and 30s cooldown","limitations":["single trading day cannot establish alpha","snapshots are not continuous L2 updates","no maker queue model","slippage stress model is assumed, not fitted"]},
 "results":results
}
(ROOT/"first-real-day-backtest.json").write_text(json.dumps(report,indent=2,ensure_ascii=False))
lines=["# TerraQuant Hyperliquid — First Genuine Orderflow Screen", "", "Historical sample: BTC 2026-09-02 00:00–24:00 UTC (one day).",f"Trades: {len(tr):,}; book rows: {len(ob):,}; snapshots: {len(bk):,}; median book interval {report['sample']['median_snapshot_spacing_s']}s.","","> No trading alpha is established by one day of data. Numbers are preliminary.", "", "| Strategy | Hold | Train N | Test N | Test mean net bps | Test win % |","|---|---:|---:|---:|---:|---:|"]
for row in results:lines.append(f"| {row['strategy']} | {row['hold_seconds']}s | {row['train_trades']} | {row['test_trades']} | {row['test_mean_net_bps']} | {None if row['test_win_rate'] is None else round(100*row['test_win_rate'],1)} |")
lines.extend(["","Fee assumption: 9 bps round-trip, plus 2 bps adverse execution; bid/ask crossing included in prices.","Sample cannot verify repeatability or 1-second execution. Needs 30–90 full continuous days with event-level L2 and out-of-sample validation."])
(ROOT/"first-real-day-backtest.md").write_text("\n".join(lines))
print("BACKTEST_COMPLETE",json.dumps({"sample":report["sample"],"results":report["results"]},default=str))
