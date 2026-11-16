/* 80 mm thermal receipt. Rendered off-screen and printed with window.print()
 * (index.css prints only `.print-receipt`). Works with any printer the tablet/PC can print to.
 */
import { createPortal } from 'react-dom'
import { formatKHR, formatUSD, usdCentsToKhr } from '../lib/money'

const CHANNEL = { QR: 'Table order', POS_DINE_IN: 'Dine-in', POS_TAKEAWAY: 'Takeaway', TELEGRAM: 'Telegram' }

export function Receipt({ order }) {
  if (!order) return null
  const paid = order.payments.find((p) => ['APPROVED', 'REFUNDED', 'PARTIALLY_REFUNDED'].includes(p.status))
  const money = (minor, cur) => (cur === 'KHR' ? formatKHR(minor) : formatUSD(minor))
  const when = new Date(order.paid_at || order.created_at)
  return createPortal(
    <div className="print-receipt fixed top-0 -left-[9999px] w-[72mm] bg-white p-2 font-mono text-[11px] leading-snug text-black" aria-hidden="true">
      <div className="text-center">
        <div className="text-[18px] font-bold tracking-[0.35em]">LAGOM</div>
        <div className="text-[9px] tracking-[0.2em]">FOOD · DRINKS · MOMENTS</div>
      </div>
      <div className="my-2 border-t border-dashed border-black" />
      <div className="flex justify-between text-[13px] font-bold">
        <span>Order #{order.number}</span>
        <span>{order.table || CHANNEL[order.channel]}</span>
      </div>
      <div>{when.toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })}</div>
      {order.created_by && <div>Cashier: {order.created_by}</div>}
      <div className="my-2 border-t border-dashed border-black" />
      {order.items.filter((i) => i.status !== 'CANCELLED').map((i) => (
        <div key={i.id} className="mb-1">
          <div className="flex justify-between gap-2">
            <span>{i.quantity} x {i.name}</span>
            <span>{formatUSD(i.line_total_usd_cents)}</span>
          </div>
          {i.options.length > 0 && <div className="pl-3 text-[10px]">{i.options.join(', ')}</div>}
          {i.special_instructions && <div className="pl-3 text-[10px]">* {i.special_instructions}</div>}
        </div>
      ))}
      <div className="my-2 border-t border-dashed border-black" />
      <Row label="Subtotal" value={formatUSD(order.subtotal_usd_cents)} />
      {order.discount_usd_cents > 0 && <Row label={`Discount${order.discount_reason ? ` (${order.discount_reason})` : ''}`} value={`-${formatUSD(order.discount_usd_cents)}`} />}
      <Row label="TOTAL" value={formatUSD(order.total_usd_cents)} bold />
      <Row label={`In riel (1$ = ${Number(order.khr_per_usd).toLocaleString('en-US')}៛)`} value={formatKHR(order.total_khr ?? usdCentsToKhr(order.total_usd_cents, order.khr_per_usd))} />
      {paid && (
        <>
          <div className="my-2 border-t border-dashed border-black" />
          <Row label={paid.method === 'cash' ? 'Paid cash' : 'Paid ABA KHQR'} value={money(paid.amount_minor, paid.currency)} />
          {paid.cash_received_minor != null && <Row label="Received" value={money(paid.cash_received_minor, paid.currency)} />}
          {paid.change_given_minor != null && <Row label="Change" value={money(paid.change_given_minor, paid.currency)} />}
          {paid.bank_reference && <Row label="ABA Trx" value={paid.bank_reference} />}
          <Row label="Ref" value={paid.reference} />
        </>
      )}
      {order.status === 'CANCELLED' && <div className="mt-2 text-center font-bold">*** CANCELLED ***</div>}
      <div className="my-2 border-t border-dashed border-black" />
      <div className="text-center">{order.receipt_footer || 'JUST THE RIGHT AMOUNT.'}</div>
    </div>,
    document.body,
  )
}

function Row({ label, value, bold }) {
  return (
    <div className={`flex justify-between gap-2 ${bold ? 'text-[14px] font-bold' : ''}`}>
      <span>{label}</span>
      <span>{value}</span>
    </div>
  )
}

/** Render the receipt, wait for the browser to lay it out, then open the print dialog. */
export function printSoon() {
  setTimeout(() => window.print(), 150)
}
