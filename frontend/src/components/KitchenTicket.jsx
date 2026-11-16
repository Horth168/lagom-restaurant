/* 80 mm kitchen ticket: big order number, table, items with options and notes.
 * Printed with window.print() like the receipt (index.css prints only `.print-receipt`). */
import { createPortal } from 'react-dom'

export function KitchenTicket({ order, station }) {
  if (!order) return null
  const when = new Date(order.paid_at || Date.now())
  return createPortal(
    <div className="print-receipt fixed top-0 -left-[9999px] w-[72mm] bg-white p-2 font-mono text-[12px] leading-snug text-black" aria-hidden="true">
      <div className="flex items-baseline justify-between">
        <span className="text-[26px] font-bold">#{order.number}</span>
        <span className="text-[11px] uppercase">{station}</span>
      </div>
      <div className="text-[16px] font-bold">{order.table || 'TAKEAWAY'}</div>
      <div className="text-[11px]">{when.toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'short' })}</div>
      <div className="my-2 border-t border-dashed border-black" />
      {order.items.map((i) => (
        <div key={i.id} className="mb-1.5">
          <div className="text-[15px] font-bold">{i.quantity} x {i.name}</div>
          {i.options.length > 0 && <div className="pl-3">{i.options.join(', ')}</div>}
          {i.special_instructions && <div className="pl-3 font-bold">! {i.special_instructions}</div>}
        </div>
      ))}
      {order.customer_note && (
        <>
          <div className="my-2 border-t border-dashed border-black" />
          <div className="font-bold">NOTE: {order.customer_note}</div>
        </>
      )}
      <div className="my-2 border-t border-dashed border-black" />
      <div className="text-center text-[10px]">LAGOM</div>
    </div>,
    document.body,
  )
}
