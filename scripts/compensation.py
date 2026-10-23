#!/usr/bin/env python3
"""北京住房公积金月缴存额计算器（只读、幂等、无副作用）

为什么存在:
    记忆库里只存了"月薪 N 税前"和"五险一金满额"这类**定性**事实。
    回答"我每月公积金多少"需要两件事：用户数据 + 政策参数。后者由
    memory/misc/北京社保公积金参数.md 提供，本脚本负责把它算出来。

边界（重要）:
    只算住房公积金。**不含五险**——北京社保缴费基数上限/比例需要单独的
    官方参数，库中尚未收录可靠来源，本脚本不臆造数字，宁可不给。

用法:
    python3 scripts/compensation.py --salary 30000 --rate 0.12 --year 2026
    python3 scripts/compensation.py --salary 30000 --all-rates
"""

import argparse

# 北京住房公积金年度参数（每年 7 月 1 日切换）——来源见 memory/misc/北京社保公积金参数.md
FUND_PARAMS = {
    2025: {"cap": 35811, "start": "2025-07-01", "end": "2026-06-30"},
    2026: {"cap": 36348, "start": "2026-07-01", "end": "2027-06-30"},
}

# 政策允许的缴存比例区间（单位自主确定，单位与个人同比例）
RATES = (0.05, 0.09, 0.10, 0.11, 0.12)


def fund_month(salary: float, rate: float, year: int) -> dict:
    """返回某年度、某比例下的公积金月缴存明细（单位/个人各一份）。"""
    cap = FUND_PARAMS[year]["cap"]
    base = min(salary, cap)          # 关键：工资高于上限时，基数被政策封顶
    personal = round(base * rate, 2)
    employer = personal              # 北京政策：单位与个人同比例、同金额
    return {
        "year": year,
        "rate": rate,
        "salary": salary,
        "cap": cap,
        "base": base,
        "capped": salary > cap,
        "personal": personal,
        "employer": employer,
        "total": round(personal + employer, 2),
    }


def render(r: dict) -> str:
    flag = f"（工资 {r['salary']:.0f} > 上限 {r['cap']}，基数已封顶）" if r["capped"] else ""
    return (
        f"{r['year']}年度 @ {r['rate']*100:.0f}%  基数 {r['base']:.0f}{flag}\n"
        f"    个人 {r['personal']:,.2f}  单位 {r['employer']:,.2f}  合计 {r['total']:,.2f} 元/月\n"
        f"    年公积金入账 {r['total']*12:,.2f} 元"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="北京公积金月缴存额计算（不含五险）")
    ap.add_argument("--salary", type=float, default=30000, help="税前月薪（示例默认值，实际请显式传入）")
    ap.add_argument("--rate", type=float, default=None, help="公积金比例，如 0.12")
    ap.add_argument("--year", type=int, default=2026, choices=sorted(FUND_PARAMS), help="公积金年度")
    ap.add_argument("--all-rates", action="store_true", help="列出政策允许的 5%%~12%% 各档")
    args = ap.parse_args()

    if args.all_rates or args.rate is None:
        for rate in RATES:
            print(render(fund_month(args.salary, rate, args.year)))
    else:
        if not (0.05 <= args.rate <= 0.12):
            ap.error("比例须在 0.05~0.12 之间（北京政策区间）")
        print(render(fund_month(args.salary, args.rate, args.year)))

    print("\n注：未计入养老/医疗/失业/工伤/生育（需北京社保基数参数，库中暂无）。")


if __name__ == "__main__":
    main()
