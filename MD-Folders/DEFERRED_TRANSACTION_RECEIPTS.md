# Deferred: printed transaction receipts

Status: Not implemented. Revisit when the owner is ready for receipt printing.

Goal: Generate a printable receipt for every recorded financial transaction so the owner can audit what happened. The requested transaction types are customer checkout, expenses, customer receivable payments, and supplier payable payments.

Before implementation, confirm the printer/paper format, required receipt details and numbering, who may print or reprint, and whether a receipt should print automatically or only when requested. Keep each receipt tied to the saved transaction; reprints must not create another payment or expense.
