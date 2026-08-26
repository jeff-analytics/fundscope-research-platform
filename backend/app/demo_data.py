import pandas as pd

QUARTERS = ["2025Q1","2025Q2","2025Q3","2025Q4","2026Q1","2026Q2"]

FUNDS = pd.DataFrame([
    ["D00001","示例科技成长混合","混合型-偏股","林泽远",186.4],
    ["D00002","示例均衡价值混合","混合型-灵活","周恺",132.7],
    ["D00003","示例制造精选混合","混合型-偏股","陈澈",104.8],
    ["D00004","示例全球机会混合","QDII-混合","许言",88.3],
], columns=["fund_code","fund_name","fund_type","manager_name","aum_yi"])

MANAGERS = pd.DataFrame([
    ["林泽远","示例资产管理",8.7,186.4,114.2,"D00001"],
    ["周恺","示例资产管理",12.4,132.7,82.5,"D00002"],
    ["陈澈","示例基金",7.1,104.8,136.7,"D00003"],
    ["许言","示例基金",10.2,88.3,91.4,"D00004"],
], columns=["manager_name","company","career_years","aum_yi","best_return_pct","fund_codes"])

BASE = {
"D00001":[
("中际旭创","300308","通信"),("新易盛","300502","通信"),("海光信息","688041","电子"),
("宁德时代","300750","电力设备"),("立讯精密","002475","电子"),("寒武纪","688256","电子"),
("美的集团","000333","家用电器"),("紫金矿业","601899","有色金属"),("招商银行","600036","银行"),("贵州茅台","600519","食品饮料")
],
"D00002":[
("招商银行","600036","银行"),("中国平安","601318","非银金融"),("紫金矿业","601899","有色金属"),
("美的集团","000333","家用电器"),("长江电力","600900","公用事业"),("贵州茅台","600519","食品饮料"),
("海尔智家","600690","家用电器"),("宁德时代","300750","电力设备"),("三一重工","600031","机械设备"),("中国移动","600941","通信")
],
"D00003":[
("宁德时代","300750","电力设备"),("汇川技术","300124","机械设备"),("三一重工","600031","机械设备"),
("比亚迪","002594","汽车"),("拓普集团","601689","汽车"),("阳光电源","300274","电力设备"),
("紫金矿业","601899","有色金属"),("中际旭创","300308","通信"),("立讯精密","002475","电子"),("美的集团","000333","家用电器")
],
"D00004":[
("腾讯控股","00700","互联网"),("阿里巴巴-W","09988","互联网"),("台积电","TSM","半导体"),
("英伟达","NVDA","半导体"),("微软","MSFT","软件"),("亚马逊","AMZN","互联网"),
("中国海洋石油","00883","能源"),("中国移动","00941","通信"),("美团-W","03690","互联网"),("小米集团-W","01810","电子")
],
}

def holdings():
    rows=[]
    for fidx,(code,items) in enumerate(BASE.items()):
        for qidx,q in enumerate(QUARTERS):
            for rank,(name,scode,sector) in enumerate(items,1):
                base=9.7-rank*0.66
                drift=((qidx-2.5)*0.08)+((fidx+rank)%4-1.5)*0.08
                share_drift=1.0
                if code=="D00001" and name in {"中际旭创","新易盛","海光信息","寒武纪"}:
                    drift+=qidx*0.34; share_drift+=qidx*(0.085 if name!="寒武纪" else 0.12)
                if code=="D00001" and name in {"贵州茅台","招商银行"}:
                    drift-=qidx*0.28; share_drift-=qidx*0.065
                if code=="D00003" and name in {"宁德时代","阳光电源"}:
                    drift-=max(qidx-2,0)*0.18; share_drift-=max(qidx-2,0)*0.055
                if code=="D00003" and name in {"中际旭创","立讯精密"}:
                    drift+=qidx*0.17; share_drift+=qidx*0.045
                # Deliberately create a few hidden-rebalancing examples: shares move while weight barely changes.
                if code=="D00001" and name=="立讯精密" and qidx>=4:
                    share_drift+=0.24*(qidx-3); drift-=0.10*(qidx-3)
                weight=max(0.65,base+drift)
                shares=max(10.0,(128-rank*7.5)*(1+fidx*.06)*max(.35,share_drift))
                market_value=shares*(4.2+rank*.45)*(1+qidx*.035)
                rows.append([code,q,scode,name,sector,round(weight,2),round(shares,2),round(market_value,2)])
    return pd.DataFrame(rows,columns=["fund_code","quarter","stock_code","stock_name","sector","weight_pct","shares","market_value_wan"])

def market_consensus():
    h=holdings()
    x=(h.groupby(["quarter","stock_code","stock_name","sector"],as_index=False)
       .agg(avg_weight=("weight_pct","mean"),demo_funds=("fund_code","nunique")))
    x["fund_count"]=(x["demo_funds"]*81+x.groupby("quarter").cumcount().map(lambda v:(v*13)%47)+x["quarter"].map({q:i*7 for i,q in enumerate(QUARTERS)}))
    x["market_value_yi"]=(x["fund_count"]*.46+x["avg_weight"]*7.2).round(1)
    return x

def sector_history():
    h=holdings();s=h.groupby(["quarter","sector"],as_index=False)["weight_pct"].sum();s["weight_pct"]=s.groupby("quarter")["weight_pct"].transform(lambda x:x/x.sum()*100);return s

def asset_history():
    return pd.DataFrame([
        ["2025Q1",68.4,23.0,8.6],["2025Q2",69.8,21.9,8.3],["2025Q3",71.0,20.9,8.1],
        ["2025Q4",72.2,20.0,7.8],["2026Q1",73.1,19.1,7.8],["2026Q2",74.0,18.5,7.5],
    ],columns=["quarter","equity","fixed_income","cash"])
