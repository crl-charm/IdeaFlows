# IdeaFlow project demonstration script

Tone: friendly, clear, and student-led. Written in English.

Suggested length: 25–35 minutes for the main walkthrough. Use the shorter route at the end if the panel gives you less time.

Based on the current committed application, including the public current-customer page. Prepared October 26, 2026. This document does not change the application or deploy anything.

## Before the demonstration — presenter notes, not speaking lines

- Use a dedicated local/demo database. Sample sales, expenses, debt payments, and stock adjustments are real writes when saved; do not rehearse them against the client's live business data.
- Use `http://127.0.0.1:5000` for this walkthrough. The public current-customer feature is committed to GitHub, but its VPS deployment has not been performed in this conversation.
- Prepare one staff account and one admin account. Use separate browser profiles for them, plus an incognito window for the public customer page. Keep passwords out of the projected screen.
- Use fake names beginning with `DEMO`, so presentation records are easy to recognize.
- Make sure today's demo records are easy to identify. Exact total examples below assume no other transactions in today's demonstration database and zero opening cash. Otherwise, explain the changes caused by the demo rather than claiming the page's entire total must match the example.
- Prepare the three sample menu items below, with enough stock or valid recipes. If using existing menu items, use their actual saved prices and update your spoken arithmetic.
- Prepare `DEMO Ana` with an unpaid ₱50 receivable dated yesterday. It will be used for the customer-suggestion and debt-history scene.
- Have a completed sample checkout from another date if you want to demonstrate switching between daily record groups.
- Test the exact accounts, pages, date filters, payment sources, and exports before presenting. Some secondary routes are older views; they are listed separately rather than mixed into the main walkthrough.
- Keep the demo under one billable hour for Carl. In the current Regular/Premium billing helper, the initial Premium charge is ₱20, followed by additional started billing blocks. Show the actual application values if the version or rules change.
- Show the timer freezing during pause. A short pause may not visibly change the peso charge because billing uses blocks rather than charging another peso every second.
- Present the midnight R2 backup and Telegram notifications as planned work. Manual R2 backups have been verified; automatic scheduling and notifications have not been enabled.
- Do not present a Remember Me checkbox, a hidden staff performance ranking, automatic bank-payment verification, or planned improvements as completed features.

### Sample story and amounts

| Example | Value |
| --- | ---: |
| Main customer | DEMO Carl |
| Space | Premium Lounge |
| Bangus Silog | ₱120 |
| Fries | ₱60 |
| Iced Latte | ₱90 |
| Final food bill | ₱270 |
| Example time bill within the first hour | ₱20 |
| Checkout total, with no discount or retained credit | ₱290 |
| Cash tendered | ₱300 |
| Change | ₱10 |
| Owner petty-cash top-up, no repayment needed | ₱300 |
| Cleaning-supplies expense paid from petty cash | ₱50 |
| Ana's previous debt + new debt | ₱50 + ₱25 = ₱75 |
| Ana's cash payment | ₱25; ₱50 remains owed |
| Demo supplier debt and partial payment | ₱200 debt; ₱100 paid; ₱100 remains |

The sample menu prices are presentation data, not a claim about the client's current menu prices. Today's checkout sale is recorded once. Ana's collection and the owner's top-up are separate cash movements.

## Opening

**Say:**

> “Good day, everyone! We're here to demonstrate IdeaFlow, our web-based management system for a coworking space and café.
>
> “The business handles two things at the same time: customers use the workspace, and they also order food and drinks. Our system brings those activities together, along with inventory, customer debts, expenses, and daily reports.
>
> “To make the demo easy to follow, we'll use one sample customer named Carl. We'll follow his visit from check-in until payment, then show how the owner reviews the records.”

**Do:** Open the public home page. Keep the staff, admin, and public-customer windows ready.

## 1. Public home page — `/`

**Say:**

> “This is the public side of IdeaFlow. Visitors can get an idea of the coworking space and the services it offers before opening the system.
>
> “The page introduces the Regular Lounge, Premium Lounge, and Boardroom. It gives the business a public-facing page, while staff operations are handled after signing in.”

**Do:** Scroll through the visible space/service information and show the navigation or login entry point. Do not claim that static promotional content is a live financial or availability report.

**Transition:** “Let's move into the staff side and follow a normal working day.”

## 2. Welcome / portal page — `/welcome`

**Say:**

> “This is the entry page for the system. It introduces the workspace and café features and gives users a way to continue to login.”

**Do:** Show the introductory panel, then click **Log in**. This page and the login page share similar introductory content, so keep this part brief.

## 3. Login page — `/login`

**Say:**

> “Staff and administrators sign in using their own accounts. That lets the system identify who is recording an action.
>
> “Staff can handle the daily operations, while administrators have additional pages for managing the business and reviewing its information. We'll start with a staff account.”

**Do:** Sign in using the prepared staff account. Point out the staff navigation after login. Keep the prepared admin session in its separate browser profile.

**Presenter note:** Do not deliberately lock an account through repeated incorrect passwords. If discussing device limits, explain that production uses one active login per staff account and up to two per admin account. Do not claim this was demonstrated on localhost when Redis lease enforcement is disabled there.

## 4. Staff Time In / Out — top navigation modal

**Say:**

> “Signing in opens the system, while Time In records the staff member's working shift.
>
> “Here, the staff member can record the start of the shift. Later, the administrator can review that staff member's Time In and Time Out history by date.”

**Do:** Open **Time In / Out**. Record Time In for the demo staff member, or show the current open shift if already timed in. Avoid creating duplicate shifts while rehearsing.

**Transition:** “Before serving customers, let's record the petty cash handed to the staff.”

## 5. Cash Boxes — top navigation modal

**Say:**

> “Let's say the owner gives the staff ₱300 for small business purchases. We enter ₱300 here as petty cash.
>
> “The form also asks whether the business needs to repay the owner. For this example, we'll choose No. The entry stays in the history with its date and recorder.
>
> “This amount adds money available for business use. It is not a customer sale, so it should not increase checkout sales.”

**Do:** Open **Cash Boxes**. Enter **300**, choose **No — no repayment is needed**, and save. Expand its history entry and show the date, amount, and recorder.

**Point out:** Enter the money once. Do not put the same physical ₱300 into both cash sources. If choosing Yes instead, explain that it creates an amount owed to the owner in Payables; that is a different example from the one used here.

**Optional line:** “If someone records the wrong amount, the correction keeps a history rather than making the original entry disappear.” Show the correction form without saving another transaction.

## 6. Dashboard — `/dashboard`

**Say:**

> “This is the staff's main working page. It shows the customers who are currently checked in, their spaces, billable time, and current time charges.
>
> “Let's check in Carl. He'll be using the Premium Lounge. Once we save, his visit appears in the active list, and the space's occupancy is updated.”

**Do:** Click **+**, enter **DEMO Carl**, select **Premium Lounge**, and check in. Show his row and the occupancy/remaining-seat information.

**Point out:** The dashboard's current bill column represents its existing time-charge view. The public customer page will show the combined time and food breakdown.

**Optional line:** “If a Time In was entered by mistake, staff can cancel it with a reason and review it under Cancelled Time Ins.” Show the dialog or history without cancelling Carl's active demo visit.

## 7. Regular, Premium, and Boardroom views — space navigation

**Say:**

> “These links help staff focus on a particular space. Regular and Premium filter the active timed customers. The Boardroom view shows customers whose room sessions have started.
>
> “An advance booking and an active visit are different. A future reservation belongs in the booking schedule until it starts.”

**Do:** Show **Regular**, **Premium**, and **Boardroom** briefly. Return to Premium or the main Dashboard to continue with Carl.

**Routes:** `/dashboard?space=Regular%20Lounge`, `/dashboard?space=Premium%20Lounge`, `/dashboard?space=Boardroom`.

## 8. Add Order — `/order/<session_id>`

**Say:**

> “Carl would also like to order a meal and fries. Instead of writing a separate bill, staff add those items directly to his current visit.
>
> “For our example, the Bangus Silog is ₱120 and the fries are ₱60, so the food amount is ₱180.”

**Do:** Click **Add Order** on Carl's row. Choose the two prepared sample items, confirm their quantities and prices, and save the order.

**Point out:** Availability depends on the item's configured inventory setup. If demonstrating meal options such as No Rice or No Egg, use a prepared supported item and explain the actual adjusted amount. Keep the main example unchanged for the later arithmetic.

## 9. Orders and order details — `/orders` and `/orders/<session_id>`

**Say:**

> “The Orders page helps staff follow the preparation of a customer's food. Opening Carl's order shows the items and their current status.
>
> “When an item is ready, staff mark it ready. Once all items are ready and the food has actually been served, staff can mark the order as served.”

**Do:** Open **Orders**, select Carl, click **Mark ready** for each item, then **Served to customer**.

**Say while showing the result:**

> “Serving the food changes its workflow status. It doesn't remove the food charge from Carl's bill.”

**Presenter note:** This detail page is currently titled **Student Orders**. Use the actual ready/served controls; do not describe an imaginary automatic kitchen or delivery integration.

## 10. Customer running-bill page — `/current-customer`

**Say:**

> “Now let's switch to the customer's view. Carl doesn't need a staff account to check his running bill. He can open this page and search for his name.
>
> “His card shows his time bill, food bill, and running total. With our current example, that is ₱20 for the space and ₱180 for food, giving a running total of ₱200.
>
> “He can expand the food details, but he cannot edit the order, pause the timer, or change the bill. Those actions stay with staff.”

**Do:** In the incognito window, open `/current-customer`, search **DEMO Carl**, and expand **View food orders**.

**Continue the live-update scene:**

> “Let's say Carl asks to pause his billable time. Staff confirm the pause on the Dashboard. On the customer page, his status changes to Paused and the billable duration stops increasing.
>
> “He can still order while paused. I'll add an iced latte for ₱90. His food bill becomes ₱270, and his running total becomes ₱290, while the time remains paused.
>
> “When he is ready to continue, staff resume his time.”

**Do:** Place the staff and customer windows side by side. Pause Carl's time and confirm. Add the iced latte through his staff order screen. Show the public page update, then resume his time. Return to Orders and mark the latte ready/served before checkout.

**Point out:** Realtime updates are preferred; visible-page refresh provides a fallback. Wait for the actual update instead of promising that every network delivers it instantly. Pause affects the time component, not the ability to order food.

**Presenter note:** The page is intentionally public: viewers can see the listed current customer names and bills. Searching a name is not an identity check. Use fake customer data in the presentation.

## 11. Checkout — Dashboard Order Summary

**Say:**

> “Carl is ready to leave, so we'll review his bill before accepting payment. The summary includes the time charge and his food orders.
>
> “For this example, the total is ₱290 with no discount or existing credit. He pays ₱300 in cash, and the system calculates ₱10 change.
>
> “We'll select the payment method that was actually used, check the amount, and confirm checkout.”

**Do:** Open Carl's **View Order** / Order Summary. Verify Time Bill **₱20**, Food Bill **₱270**, and Total **₱290**. Select **Cash**, enter **300**, and complete checkout.

**Show the result:** Carl leaves the active Dashboard and public current-customer list. His completed transaction remains available in the records.

**Optional discount explanation:** “If an applicable discount is selected, staff review the adjustment before completing payment.” Show that separately in rehearsal; do not claim every discount applies to the entire bill or change this example midway.

**Payment note:** Cash, GCash, BDO, BPI, and QueenBank are recorded payment methods. Selecting one records how payment was received; it does not itself transfer or independently verify money through a banking API.

## 12. Receipt — `/receipt/<session_id>`

**Say:**

> “This is Carl's receipt. It summarizes his visit, food charges, total payment, and change.
>
> “It gives staff and the customer a record they can review after the transaction.”

**Do:** Open the completed visit's receipt from the available checkout/records link, or the prepared receipt URL. Point to the saved amounts and the payment method. Show printing only if the demonstration printer or browser print preview has been tested.

## 13. Checkout Records — `/checkout-records`

**Say:**

> “The Dashboard shows customers who are still active. Checkout Records is where we look for completed transactions.
>
> “We can select a date and view the checkouts from that Manila business day. Carl's checkout is now here, together with his bills, payment method, and the staff member who collected the payment.
>
> “Changing the date changes what we see; it doesn't delete the other records.”

**Do:** Select **Today**, find Carl, show his total, and switch to the other prepared date. Return to today.

**Optional correction scene:** Show how a staff member requests a void and how an administrator reviews a prepared request. Do this as a separate rehearsed scenario; approving a real refund or reopening Carl's checkout would change the rest of this demo's totals.

## 14. Food Orders — `/food-orders`

**Say:**

> “Some customers order food without using a timed coworking session. Food Orders handles that situation, including a take-out customer.
>
> “The important difference is that a food-only order does not build up a space-time bill.”

**Do:** Open **Food Orders**, click **New Food Order**, and show the name/location fields. For the main numerical walkthrough, close the form without saving a second sale.

**If demonstrating the full food-only flow:** Create **DEMO Takeout**, add an available item, and show that the time charge is zero. Explain that any completed extra sale must also be included in the report figures; do not keep quoting ₱290 as the entire day's checkout sales afterwards.

## 15. Space Bookings — `/lounge-booking`

**Say:**

> “Space Bookings handles room reservations. Staff can record the customer, booking type, date, time, and group size, then review the schedule.
>
> “Let's create a sample Boardroom reservation for tomorrow. It appears in the schedule, but it is not an active customer visit yet.
>
> “The system also provides a walk-in option. When a booking starts, its linked visit can be handled by staff. Changes can be reviewed in its history.”

**Do:** Click **New Booking**. Use **DEMO Study Group**, tomorrow's date, an available 10:00–11:00 a.m. slot, and a group size within the configured room capacity. Review and save the reservation.

**Point out:** Show the Boardroom/Whole Hub booking options only if they are visible and prepared. Show history and extension controls on an appropriate existing example. Do not start tomorrow's booking just to make it appear active during the presentation.

## 16. Menu management — `/staff/menu` or `/admin/menu`

**Say:**

> “This is where the business maintains the items it sells. Staff can review the item's name, category, price, and availability, while the inventory setup determines how its stock is handled.
>
> “These are the same items we used in Carl's order. Keeping menu information in one workspace helps staff use consistent item details instead of typing a different price for every customer.”

**Do:** Search for the prepared Bangus Silog, fries, and latte. Open one item's details/edit form and explain the visible settings. Cancel if no change is needed.

**Presenter note:** Do not change the sample prices halfway through the story. Saved order prices and current catalog prices serve different purposes. Use actual configured item types when explaining recipes or untracked items.

## 17. Inventory — `/staff/inventory` or `/admin/inventory`

**Say:**

> “Inventory helps the business keep track of ingredients and available items. Here, we can see quantities, units, and the history of stock actions.
>
> “For items linked to stock or recipes, orders affect their available quantities. The history helps the owner see what changed, when it changed, and who recorded it.
>
> “Staff can also review the kitchen and meal information available to their account.”

**Do:** Find one prepared ingredient or tracked item. Show its quantity/unit and an existing restock, production, or order-related history entry. Show the meal/day audit controls if configured. Demonstrate a stock adjustment only with a separate demo item and an appropriate reason.

**Point out:** Creating a payable does not automatically prove stock was received. Inventory receipt and supplier payment are different operations. Do not claim every menu item has ingredient tracking unless it is actually configured.

## 18. Expenses — `/expenses-view` or `/admin/expenses`

**Say:**

> “Now let's record money spent by the business. For example, staff bought ₱50 worth of cleaning supplies using the petty cash we entered earlier.
>
> “We record the expense details, amount, payment method, and cash source. Since this came from petty cash, the available petty cash changes from ₱300 to ₱250.”

**Do:** Log **DEMO Cleaning Supplies**, amount **50**, a suitable category, **Cash**, and **Petty cash box**. Save and show the recorded actor/date. Reopen Cash Boxes briefly to show the updated petty cash amount.

**Point out:** Owner-paid-directly and business cash sources have different effects. Keep this example on Petty cash box. Show a correction/void dialog only if rehearsed; do not void the ₱50 example if continuing with the reference totals.

## 19. Receivables / Customer Utang — `/receivables-view`

**Say:**

> “Receivables records money customers still owe the business. Let's use Ana as a separate example. She already owes ₱50 from yesterday, and today she takes another ₱25 on credit.
>
> “When staff type her name, the system can suggest the existing customer. We select her open tab so the new entry joins the correct debt cycle. The recorder is taken from the signed-in staff account.
>
> “Ana now owes ₱75 in total. If she pays ₱25 in cash, we record that payment and her remaining balance becomes ₱50.”

**Do:** Stay in the **staff** window. Select today, click **New Receivable**, search **DEMO Ana**, select the prepared existing open tab, and add a new **₱25** debt with today's Date Taken and a suitable due date. Record a **₱25 Cash** tab payment. Open the tab history.

**Continue:**

> “The date filter tells us when the debts were taken. Payment history tells us when money was collected. Those dates can be different.
>
> “The customer tab keeps the all-date balance visible. Collections are recorded separately from new checkout sales, so Ana's ₱25 payment should not be counted as another checkout.”

**Point out:** Tab payments apply to older unpaid debt first. A fully settled tab can leave the active list while its history remains. Use the prepared settled example if showing this without changing today's cash figures.

**Presenter note:** Use the staff-entry path for this scene and rehearse it. The codebase review identified an unresolved admin receivable actor-ID issue; this script does not claim that every admin creation path has already been corrected.

## 20. Payables — `/staff/payables` or `/admin/payables`

**Say:**

> “Payables is the other side of the debt records: money the business owes to a supplier or, where applicable, the owner.
>
> “For example, the business owes a supplier ₱200. We'll record a ₱100 payment using the customer cash box, leaving ₱100 still payable.
>
> “The payment history shows the source and recorder, so the owner can follow where the money went.”

**Do:** Create or use **DEMO Supplier**, with an unpaid **₱200** balance. Record **₱100 Cash**, paid from **Customer cash box**, using the business-funded option. Show the remaining ₱100 and payment history.

**Point out:** Only the actual payment reduces held cash. Do not enter the same supplier payment again as a separate ordinary expense merely to make it appear in two places.

## 21. Daily Balance — `/staff/daily-balance` or `/admin/daily-balance`

**Say:**

> “Daily Balance brings today's recorded activity together. This is where the owner can review the coworking charges, café charges, discounts, collections, spending, and cash movement.
>
> “For Carl's completed checkout, we have ₱20 for Cowork and ₱270 for Cafe. There was no discount, so checkout sales are ₱290.
>
> “Ana's ₱25 payment is a debt collection. The owner's ₱300 is cash added. These affect the money we track, but we keep them separate from checkout sales.”

**Do:** Select **Today**. Show **Live Summary**, **Receivables Collected**, **Today's Cash Movement**, **Still to Collect**, and **Projected Cash Movement**. Explain that the last two refer to active unpaid visit bills/estimates, not completed money already received.

**Continue with the cash example:**

> “Using only our sample transactions, ₱300 owner cash added plus ₱290 cash received from Carl plus ₱25 collected from Ana gives ₱615 coming in.
>
> “We then subtract ₱50 for the cleaning supplies and ₱100 paid to the supplier. That leaves ₱465 of cash movement for our example.
>
> “The petty cash portion is ₱250, and the customer cash portion is ₱215. Their combined expected balance is ₱465. These are recorded cash figures; the staff still need to compare them with the money physically present.”

**Do:** Expand **Cash boxes by Manila day** and **Payment method reconciliation**. Show **Cash**, expand its details, and explain the amounts. Show the zero-method toggle if available rather than presenting a large sideways-scrolling table.

### Daily reports and AM/PM soft balances — same page

**Say:**

> “The date controls let us review a particular day or a range. We can generate a daily report, expand its details, and export it as PDF, Excel, or CSV.
>
> “AM and PM soft balances give the business saved checkpoints during the day. We can see who recorded a checkpoint, its notes, and whether the live figures later differ from that saved snapshot.”

**Do:** Expand a prepared daily report and an AM/PM entry. If creating them during the demo, use clear demo notes and valid inputs. Generate today's report and open one tested export. Explain the other formats without opening three downloads in succession.

**Presenter note:** Report figures above assume only the listed sample transactions, all paid in cash, zero openings, no extra food-only checkout, no refund, no withdrawal, no owner repayment, and no other finance adjustment. Do not call cash movement or checkout sales “final profit.”

## 22. Admin Panel — `/admin`

**Say:**

> “Let's switch to the administrator's view. The owner can review business information and manage staff accounts from the Admin Panel.
>
> “The staff directory shows the registered staff. The owner can add or update staff details and review records instead of sharing one account with everyone.”

**Do:** Use the separate admin browser profile. Show the staff directory and **Add New Staff** form, then cancel unless a prepared demo account is needed.

### Staff Time In/Out history

**Say:**

> “Here, the owner can choose a date and review staff Time In and Time Out events. This connects back to the shift we recorded at the start of the demo.”

**Do:** Open **Staff Time In/Out** through the staff summary/control, filter today, and show the demo staff member's event. Show another prepared date if available.

### Active Login Sessions

**Say:**

> “The owner can also review active login sessions. This is about access to the system, while the Time In/Out record is about the employee's working shift.”

**Do:** Open **Active Login Sessions**. Show the current entries without signing out the staff browser used for the demonstration.

### Space settings and customer records

**Say:**

> “The Admin Panel also provides customer records and space capacity and price settings for the business to review.”

**Do:** Show **Customer Records**, **Space Capacity Management**, and **Space Price Management**. Keep configuration changes out of the main numerical story. Do not promise that changing a field retrospectively recalculates saved transactions, and verify actual billing behavior before demonstrating a price change.

**Presenter note:** The Add Staff form creates staff accounts. Do not describe it as an unrestricted admin-account creation form. The separate client-admin migration is an implementation detail, not a page to demonstrate here.

## 23. Analytics — `/analytics`

**Say:**

> “Analytics gives the owner a broader view of the business. Instead of looking at one transaction, we can review revenue trends, top-selling food, and customer activity for the selected dates.
>
> “For example, these summaries can help the owner notice which items are selling and which periods are more active. They support a business decision; they don't guarantee what will happen next.”

**Do:** Choose a date range containing demo data. Show **Daily Revenue Flow**, **Top Selling Foods**, and **Top Customers**. If asked, open the all-time customer view and explain that it covers a different period from a short date filter.

**Point out:** Customer activity summaries are different from the staff performance ranking that was removed from the main navigation. Do not reintroduce that hidden ranking as part of this walkthrough.

## 24. Profile, Time Out, and Logout — `/profile`, staff modal, `/logout`

**Say:**

> “Profile shows the signed-in user's name, username, and role, so staff can confirm which account they are using.
>
> “At the end of the shift, staff record Time Out. When they finish using the system, they sign out.”

**Do:** Return to the staff browser, open **Profile**, then record **Time Out** through the staff control and click **Logout**. In the admin window, show the completed shift history if time allows. Close or hide other signed-in demonstration windows when finished.

**Point out:** The current Profile page displays account details. Do not promise an edit-profile/password-change control that is not on that screen.

## Optional mobile/PWA scene

**Say:**

> “The system can also be used through a phone browser. The layout adapts to a smaller screen, and supported browsers offer a home-screen installation option.
>
> “For staff, this gives another way to open the same system when a computer isn't available. It still needs the server and an internet connection for live business data.”

**Do:** Show a rehearsed phone or narrow browser view. Point out the navigation drawer, readable cards, and Cash Boxes controls. Demonstrate installation only on a supported device you have already tested. Do not describe the PWA as a separate native app or an offline POS.

## Closing

**Say:**

> “That completes our walkthrough of IdeaFlow. We followed Carl from check-in and food ordering to viewing his bill, paying, and appearing in the daily records.
>
> “We also showed how staff record expenses and debts, while the owner reviews reports, inventory, staff history, and business activity.
>
> “Our goal is to make these daily tasks easier to follow in one system, with a record of the actions being made. Thank you, and we're ready for your questions.”

## Extra pages, only if they are part of the requested coverage

These routes exist in the repository but are not all part of the main sidebar flow. Rehearse them first. Some are alternate or older workspaces. Browsing them is not a reason to make extra financial or account-role changes during a presentation.

| Route | Friendly speaking line | What to show |
| --- | --- | --- |
| `/menu` | “This is an alternate ordering catalog where staff can browse the available food items.” | Item cards and availability; use the per-customer order flow for the main story. |
| `/menu-view` | “This view gives staff a simpler list of menu information.” | Existing items and prices. The main operational Menu workspace is `/staff/menu`. |
| `/inventory` | “This is another staff inventory and kitchen view available in the codebase.” | Existing quantities, available kitchen controls, and day-audit information permitted for that account. |
| `/boardroom` | “This is an alternate Boardroom booking page.” | A prepared booking list/form; use Space Bookings for the main reservation demonstration. |
| `/finance` | “This additional administrator page summarizes budgets and recorded finance transactions.” | Budget, allocated/spent/remaining figures, and transaction list. |
| `/finance/budget` | “Here, we can review the budget information presented by this finance workspace.” | The rendered budget summary; do not promise editing controls unless present. |
| `/finance/expenses` | “This is an additional finance view of spending and transactions.” | Existing records. The main expense-entry scenes are Expenses and Daily Balance. |
| `/finance/reports` | “This route presents the finance summary and its report output.” | Summary/export already tested for the selected data. |
| `/management` | “This additional administrator workspace gives a management summary.” | Read-only summary. |
| `/management/users` | “This page lists users for administrative review.” | User list only. Use the Admin Panel for the staff-management scene. |
| `/management/settings` | “This settings route currently presents the shared management summary.” | What the page actually renders; do not invent additional settings. |
| `/daily-sales` | “This shortcut opens Daily Balance for the signed-in role.” | The destination page; it is a redirect, not a separate sales report to explain twice. |

Admin/staff aliases of Menu, Inventory, Payables, and Daily Balance reuse the relevant workspaces. Show the staff experience first and explain the matching admin access rather than repeating the same complete demonstration twice. Receivables and Expenses have role-specific views, so briefly compare their presentation if the panel requests both.

The hidden `/admin/staff-performance` route is outside the recommended presentation. Its old ranking page remains in code, while the requested primary navigation/ranking removal has already been made. The legacy management role editor also has an unresolved authentication-role finding; do not claim arbitrary role changes are a verified supported workflow.

## Quick answers for likely panel questions

**“Why combine coworking and café transactions?”**

> “One customer can use a space and order food during the same visit. Linking them helps staff review the charges together and see the completed checkout in the records.”

**“Does pausing time stop food ordering too?”**

> “No. It pauses the billable duration. Food can still be added and charged to the visit.”

**“Can customers change their own bill?”**

> “The public bill page is for viewing only. Changes such as orders, pausing, and checkout are handled through signed-in staff actions.”

**“Is the running bill the final amount?”**

> “It shows the current time and food total before checkout adjustments. Staff review discounts and any existing credit when completing payment.”

**“Does choosing GCash automatically transfer the payment?”**

> “The current system records the payment method. Staff still confirm the actual payment; this demonstration does not include an automatic banking integration.”

**“Are sales and cash on hand the same?”**

> “No. A sale can be paid digitally. Cash can also come from an owner top-up or an old debt collection, and some cash is used for expenses or payments. We track those sources separately.”

**“Does the system already back itself up every midnight?”**

> “We have verified manual database and file backups to Cloudflare R2. A midnight schedule and Telegram failure alerts are documented in the next implementation plan, but they are not enabled yet.”

**“What happens if a page cannot refresh?”**

> “We check the connection and the page's update status. The public bill page keeps its last successful data and marks an update failure instead of showing a false zero. If an action reports an error, we verify its saved history before trying the same payment again.”

**“Will it work on every device without any errors?”**

> “The layout supports mobile browsers, and we have automated and browser checks for important workflows. We still test the actual devices and network conditions the client will use. We wouldn't promise that any web application can never encounter an error.”

## If you have only 10–15 minutes

Use this route, keeping the same student-friendly speaking lines above:

1. Opening, public page, and staff login.
2. Staff Time In and the ₱300 petty-cash entry.
3. Check in Carl and add the first food order.
4. Show the public bill beside the staff page; pause, add the latte, and resume.
5. Checkout, receipt, and today's Checkout Records.
6. Briefly show the Menu, Inventory, and Space Bookings screens without extra writes.
7. Explain one prepared Expense, Receivable, and Payable record.
8. Show Daily Balance and one export, then Admin Panel/Analytics.
9. Staff Time Out, Logout, and closing.

If you skip sample payments or expenses to save time, also skip the ₱465 final-cash claim. Use the actual recorded example figures instead.

## Delivery reminders

- Speak to the panel, then click; give them a moment to see the result before moving on.
- Explain what a feature helps the staff/customer/owner do, rather than reading every label aloud.
- Use one presenter at a time. A second member can operate the other browser window for the live-bill scene.
- If a view is empty, check the selected date and demo setup; an empty date range is not evidence that records were deleted.
- If something genuinely fails, say: “This part needs checking. I'll show the last verified result and continue with the next workflow.” Do not pretend a failed action succeeded or click a payment repeatedly.
- Present the working application first. Keep source-code discussions, server credentials, and detailed backup setup out of the projected business walkthrough.
