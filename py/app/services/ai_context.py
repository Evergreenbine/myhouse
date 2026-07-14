from datetime import date
import re

import local_db as db


def ai_money(value):
    try:
        return f"{float(value or 0):.2f}"
    except Exception:
        return "0.00"


def ai_status_label(status):
    labels = {
        "empty": "未录入",
        "draft": "录入中",
        "pending": "待发送",
        "pending_payment": "待收款",
        "unpaid": "未收",
        "partial": "部分收款",
        "paid": "已收",
    }
    return labels.get(status or "", status or "未知")


def ai_shift_month(base_date, offset):
    month_index = base_date.year * 12 + base_date.month - 1 + offset
    year = month_index // 12
    month = month_index % 12 + 1
    return f"{year:04d}-{month:02d}"


def ai_extract_months(prompt):
    today = date.today()
    text = prompt or ""
    months = set()
    if any(k in text for k in ("本月", "这个月", "当月", "当前月")):
        months.add(today.strftime("%Y-%m"))
    if any(k in text for k in ("上月", "上个月", "上个账期")):
        months.add(ai_shift_month(today, -1))
    if any(k in text for k in ("下月", "下个月", "下个账期")):
        months.add(ai_shift_month(today, 1))
    for y, m in re.findall(r"(20\d{2})[-年/](1[0-2]|0?[1-9])", text):
        months.add(f"{int(y):04d}-{int(m):02d}")
    for m in re.findall(r"(?<!\d)(1[0-2]|0?[1-9])月", text):
        months.add(f"{today.year:04d}-{int(m):02d}")
    if not months:
        months.add(today.strftime("%Y-%m"))
    return sorted(months)


def ai_payment_total(payments):
    total = 0.0
    for p in payments or []:
        try:
            total += float(p.get("amount") or 0)
        except Exception:
            pass
    return total


def build_rental_ai_context(prompt):
    months = ai_extract_months(prompt)
    buildings = db.get_buildings() or []
    contracts = db.get_contracts(True) or []
    payments = db.get_payments() or []
    lines = [
        f"今天: {date.today().isoformat()}",
        f"查询账期: {', '.join(months)}",
        "状态含义: 未录入=没有账单；录入中=draft；待发送=pending；待收款=pending_payment；未收=unpaid；部分收款=partial；已收=paid；待收金额=应收-已收。",
    ]

    if buildings:
        lines.append("楼栋: " + "；".join([f"{b.get('id')}:{b.get('name', '')}" for b in buildings[:30]]))
    else:
        lines.append("楼栋: 暂无")

    lines.append(f"有效合同数: {len(contracts)}")
    if contracts:
        lines.append("有效合同明细:")
        for c in contracts[:80]:
            lines.append(
                f"- 合同{c.get('id')}: {c.get('building_name', '')}/{c.get('room_number', '')}，"
                f"租客{c.get('tenant_name', '')}，月租{ai_money(c.get('monthly_rent'))}，"
                f"水价{ai_money(c.get('water_unit_price'))}，电价{ai_money(c.get('electric_unit_price'))}"
            )
        if len(contracts) > 80:
            lines.append(f"- 其余有效合同 {len(contracts) - 80} 条未展开")

    for month in months:
        bills = db.get_bills(month) or []
        bill_map = {}
        payment_totals = {}
        for b in bills:
            try:
                bill_map[int(b.get("contract_id"))] = b
                bid = int(b.get("id"))
                payment_totals[bid] = ai_payment_total(db.get_payments(bid))
            except Exception:
                pass

        expected = paid = due = 0.0
        status_counts = {}
        detail_lines = []
        for c in contracts:
            cid = int(c.get("id"))
            bill = bill_map.get(cid)
            if bill:
                status = bill.get("status") or "unpaid"
                amount = float(bill.get("total_amount") or 0)
                bill_id = int(bill.get("id") or 0)
                paid_amount = payment_totals.get(bill_id, 0.0)
                if status == "paid" and paid_amount <= 0:
                    paid_amount = amount
                paid_amount = min(paid_amount, amount)
                due_amount = max(amount - paid_amount, 0.0)
                row = (
                    f"- {c.get('building_name', '')}/{c.get('room_number', '')} {c.get('tenant_name', '')}: "
                    f"{ai_status_label(status)}，应收{ai_money(amount)}，"
                    f"已收{ai_money(paid_amount)}，待收{ai_money(due_amount)}，"
                    f"房租{ai_money(bill.get('rent_amount'))}，水费{ai_money(bill.get('water_fee'))}，"
                    f"电费{ai_money(bill.get('electric_fee'))}"
                )
            else:
                status = "empty"
                amount = float(c.get("monthly_rent") or 0)
                paid_amount = 0.0
                due_amount = amount
                row = (
                    f"- {c.get('building_name', '')}/{c.get('room_number', '')} {c.get('tenant_name', '')}: "
                    f"未录入，预计月租{ai_money(amount)}，待收{ai_money(due_amount)}"
                )
            expected += amount
            paid += paid_amount
            due += due_amount
            status_counts[status] = status_counts.get(status, 0) + 1
            detail_lines.append(row)

        status_order = ["empty", "draft", "pending", "pending_payment", "unpaid", "partial", "paid"]
        status_summary = "，".join([
            f"{ai_status_label(k)}{status_counts.get(k, 0)}户"
            for k in status_order
            if status_counts.get(k, 0)
        ])
        summary_parts = [
            f"应收{ai_money(expected)}",
            f"已收{ai_money(paid)}",
            f"待收{ai_money(due)}",
            f"未收/未完成{len(contracts) - status_counts.get('paid', 0)}户",
        ]
        if status_summary:
            summary_parts.append(status_summary)
        lines.append(f"{month} 账单汇总: " + "，".join(summary_parts))
        lines.append(f"{month} 账单明细:")
        lines.extend(detail_lines[:100])
        if len(detail_lines) > 100:
            lines.append(f"- 其余明细 {len(detail_lines) - 100} 条未展开")

    if payments:
        lines.append("最近收款记录:")
        for p in payments[:30]:
            lines.append(
                f"- 账单{p.get('bill_id')}: {p.get('billing_month', '')}，"
                f"金额{ai_money(p.get('amount'))}，日期{p.get('pay_date', '')}，方式{p.get('pay_method', '')}"
            )
    else:
        lines.append("最近收款记录: 暂无")

    return "\n".join(lines)

