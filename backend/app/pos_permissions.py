PERMISSIONS = {
    "orders.assign",
    "orders.transfer",
    "orders.split",
    "orders.merge",
    "orders.request_bill",
    "kitchen.cancel",
    "kitchen.adjust",
    "kitchen.tickets.create",
    "kitchen.tickets.view",
    "kitchen.all_areas",
    "receipts.preview",
    "reports.operational",
}

ROLE_OPERATIONS = {
    "waiter": {
        "orders.request_bill",
        "kitchen.tickets.create",
        "kitchen.tickets.view",
        "receipts.preview",
    },
    "cashier": {
        "orders.request_bill",
        "orders.split",
        "orders.merge",
        "receipts.preview",
        "tables.view",
    },
    "cook": {"kitchen.tickets.view"},
}
