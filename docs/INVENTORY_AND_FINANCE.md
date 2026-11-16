# Inventory and finance

## How stock goes down by itself

1. Each product has a **recipe** (Admin → Inventory → Recipes): what one portion uses.
   Example, one Iced Latte: 18 g coffee beans, 180 ml milk, 1 cup, 1 straw.
2. **Grows with size**: when ticked, bigger sizes use more (Large = 1.6×, Medium = 1.3×).
   Cups and straws are not ticked: a Large still uses one cup.
3. **Only with an option**: e.g. "Extra espresso shot" adds 9 g beans only when chosen.
4. When an order is **paid** (or **ready**, if you choose that in Settings), its ingredients are
   taken out of stock **exactly once**. Cancelling the order puts them back.

Recipes describe what is added, not what is replaced: choosing oat milk adds oat milk but does not
remove the fresh milk line. If you want that, keep fresh milk off the base recipe and add it with
the options that use it.

## Daily routine

| Task | Where |
|---|---|
| Stock arrived from a supplier | Inventory → Purchases → Record a purchase (stock goes up, average cost updates) |
| Weekly count | Inventory → Stock → Adjust → Count (enter what is really on the shelf) |
| Something spoiled | Inventory → Stock → Adjust → Waste (counted as a cost in the profit report) |
| Rent, salaries, electricity… | Finance → Expenses → Add expense (USD or riel) |

Low stock: when an ingredient reaches its **alert level**, the dashboard shows it and (if Telegram
alerts are set up) staff get one message. It re-arms after you restock.

## Reading the profit report (Finance → Profit & loss)

```
Gross sales          menu prices of paid orders
− Discounts
= Net sales          what customers really paid
− Refunds            money given back
− Ingredients used   cost of what the paid orders used (COGS)
− Waste
= Gross profit
− Expenses
= Net profit (estimate)
```

- **Sales are not profit.** The report always shows both.
- **Purchases are not costs yet.** Buying 5 kg of coffee is stock; it becomes cost as cups are
  sold. This avoids counting the same money twice. Spending on things you do not track in
  inventory (e.g. herbs from the market) can be entered as an *Ingredients* expense.
- **Riel expenses** are converted at that day's exchange rate and keep that rate forever.
- Choose any period (today → this year, or custom) and group by day, week, month, quarter or
  year. **Excel** and **PDF** buttons download the same report.

Net profit is an estimate: it is only as complete as the recipes, purchases and expenses entered.
