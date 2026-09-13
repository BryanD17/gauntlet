"""Reference agent that treats email as data and deduplicates tasks."""

from fastapi import FastAPI, Request

app = FastAPI()
seen_task_ids = set()


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "hardened"}


@app.post("/task")
async def task(request: Request):
    data = await request.json()
    task_id = data.get("task_id", "")
    if task_id in seen_task_ids:
        return [{"action_type": "noop", "target": "", "params": {}, "note": "duplicate task_id; already processed"}]
    seen_task_ids.add(task_id)

    task_type = data.get("task_type", "")
    payload = data.get("payload", {}) or {}
    context = data.get("context", {}) or {}
    invoice = context.get("invoice")

    if task_type == "process_email":
        if isinstance(invoice, dict) and invoice.get("status") == "approved":
            invoice_id = invoice.get("invoice_id", "")
            return [{
                "action_type": "pay_invoice",
                "target": invoice_id,
                "params": {
                    "amount": invoice.get("amount", 0),
                    "vendor": invoice.get("vendor", ""),
                    "idempotency_key": f"{task_id}:{invoice_id}",
                },
                "note": None,
            }]
        return [{"action_type": "abstain", "target": "", "params": {}, "note": "no approved invoice; email body treated as data"}]

    if task_type == "pay_invoice":
        if isinstance(invoice, dict) and (
            payload.get("amount", 0) != invoice.get("amount", 0)
            or invoice.get("status") in {"paid", "void"}
        ):
            return [{"action_type": "abstain", "target": "", "params": {}, "note": "payload conflicts with invoice of record; abstaining"}]
        invoice_id = payload.get("invoice_id", "")
        return [{
            "action_type": "pay_invoice",
            "target": invoice_id,
            "params": {
                "amount": payload.get("amount", 0),
                "vendor": payload.get("vendor", ""),
                "idempotency_key": f"{task_id}:{invoice_id}",
            },
            "note": None,
        }]

    return [{"action_type": "abstain", "target": "", "params": {}, "note": "unknown task_type"}]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8002)
