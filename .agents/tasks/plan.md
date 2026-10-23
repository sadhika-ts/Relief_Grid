# Implementation Plan: Remaining Demand Management System

## Overview
Build a comprehensive system to track partial fulfillment, manage outstanding demand, support multiple deliveries per request, and provide reallocation workflows when new stock arrives.

## Feature Decomposition
This work is decomposed into 4 features (FEAT-001 through FEAT-004) that build on each other. See the FEAT JSON files in `.agents/tasks/remaining-demand-management/features/` for detailed implementation steps.

---

## FEAT-001: Database Schema Changes

- [ ] 1. Add tracking columns to requests table in db.py SCHEMA
      Add total_allocated, total_dispatched, total_received (all INTEGER DEFAULT 0) after allocated_qty column
      Files: db.py
      Verify: Delete reliefgrid.db, run `python app.py`, use `sqlite3 reliefgrid.db '.schema requests'` to confirm columns exist

- [ ] 2. Update finalize_request() to track total_allocated
      When creating a delivery, add allocated qty to existing total_allocated
      Files: app.py (finalize_request function around line 106)
      Verify: Apply an allocation via /admin/allocations and check database that total_allocated equals allocated_qty for new requests

- [ ] 3. Update advance_delivery() to track total_received and update status
      When delivery status becomes 'Delivered', increment total_received, calculate remaining = quantity - total_received, set status to 'Partially Fulfilled' if remaining > 0 else 'Fulfilled'
      Files: app.py (advance_delivery route around line 279)
      Verify: Advance a delivery to Delivered status and verify request status updates correctly based on remaining demand

---

## FEAT-002: Enhanced Allocation Algorithm

- [ ] 4. Update pending_requests() to include partially fulfilled requests
      Change WHERE clause from "status = 'Pending'" to "status IN ('Pending', 'Partially Fulfilled')"
      Add computed field: remaining_demand = quantity - total_received
      Files: app.py (pending_requests function around line 84)
      Verify: Manually set a request to 'Partially Fulfilled' with total_received < quantity, run allocation, verify it appears in the plan

- [ ] 5. Modify allocations route to allocate against remaining demand
      For each request from pending_requests(), if status is 'Partially Fulfilled', pass remaining_demand as the quantity to allocate()
      Files: app.py (allocations route around line 262)
      Verify: Apply allocation that partially fulfills a request, add new stock, run allocation again, verify remaining demand is allocated

- [ ] 6. Update allocations.html template to show remaining demand
      Add 'Remaining' column, show original quantity vs remaining for partially fulfilled requests
      Add visual indicator (pill) to distinguish reallocations from new requests
      Files: templates/allocations.html
      Verify: View /admin/allocations with partially fulfilled requests and confirm remaining demand is clearly displayed

---

## FEAT-003: Outstanding Demand Dashboard & UI Updates

- [ ] 7. Create /admin/outstanding route
      Query all requests with (quantity - total_received) > 0
      Calculate days_waiting from created_at timestamp
      Join with locations, resources, users tables
      Pass to outstanding.html template
      Files: app.py (new route after allocations route)
      Verify: Navigate to /admin/outstanding and verify requests with remaining demand appear

- [ ] 8. Create templates/outstanding.html
      Table with columns: location, resource, requested, received, remaining, urgency, days waiting
      Add progress bar: `<div class="bar"><i style="width: X%"></i></div>` where X = (received/requested * 100)
      Flag critical requests waiting > 3 days with red styling
      Files: templates/outstanding.html (new file)
      Verify: Check page displays all columns correctly with progress bars rendering properly

- [ ] 9. Add Outstanding Demand to navigation
      Insert ('Outstanding', 'outstanding') in ADMIN_NAV list between 'Allocations' and 'Deliveries'
      Files: app.py (ADMIN_NAV constant around line 20)
      Verify: Login as admin and confirm 'Outstanding' link appears in sidebar navigation

- [ ] 10. Update admin dashboard with outstanding demand metrics
      Add two new stat cards: 'Outstanding Demand' count (requests with remaining > 0) and 'Critical Shortages' count (critical urgency + waiting > 3 days)
      Files: app.py (admin_dashboard route around line 128), templates/admin_dashboard.html
      Verify: View /admin dashboard and confirm new stat cards appear with correct counts

- [ ] 11. Add 'Partially Fulfilled' filter to admin requests page
      Add 'Partially Fulfilled' to status filter buttons
      Add 'Remaining' column showing (quantity - total_received)
      Files: templates/admin_requests.html
      Verify: Click 'Partially Fulfilled' filter and verify filtered results appear correctly

- [ ] 12. Update user request views to show progress
      Add 'Received' column showing total_received
      Add progress indicator (percentage or bar)
      Files: templates/my_requests.html
      Verify: Login as relief user (riverside@ngo.org/relief123) and view /my/requests to confirm progress display

---

## FEAT-004: Multi-Delivery Support & Reallocation Workflow

- [ ] 13. Complete advance_delivery() multi-delivery logic
      Ensure when advancing to 'Delivered', total_received increments by delivery quantity
      Verify status updates to 'Partially Fulfilled' or 'Fulfilled' based on remaining demand
      Files: app.py (advance_delivery route - should be complete from FEAT-001, verify it works)
      Verify: Deliver multiple deliveries for same request and confirm total_received accumulates correctly

- [ ] 14. Update delivery_feedback() for relief user confirmation
      When user confirms receipt (confirmed=1), ensure total_received is incremented if not already done
      Update request status appropriately
      Files: app.py (delivery_feedback route around line 338)
      Verify: Login as relief user, confirm delivery receipt, check request status updates

- [ ] 15. Add reallocation button to inventory page
      Add button 'Reallocate Outstanding Demand' that links to /admin/allocations
      Add flash message explaining both new and outstanding requests will be included
      Files: templates/inventory.html
      Verify: View /admin/inventory page and confirm button appears and links correctly

- [ ] 16. Update allocations template with reallocation indicators
      Add pills to distinguish 'NEW' (Pending) vs 'REALLOCATION' (Partially Fulfilled)
      Add explanatory note about reallocation workflow
      Files: templates/allocations.html
      Verify: View allocations with mix of pending and partially fulfilled requests, confirm visual distinction

- [ ] 17. Add delivery numbering to delivery pages
      Show which delivery number this is for the request (1st, 2nd, etc.)
      Files: templates/admin_deliveries.html, templates/my_deliveries.html
      Verify: View deliveries page with multiple deliveries for same request and confirm numbering appears

---

## Verification Steps (End-to-End)

After completing all features:

1. **Reset and start fresh**
   ```bash
   rm reliefgrid.db
   python app.py
   ```

2. **Test partial allocation workflow**
   - Login as admin (admin@reliefgrid.org / admin123)
   - View /admin/allocations
   - Apply allocation (some requests will be partially fulfilled due to stock limits)
   - Verify requests show 'Partially Approved' status

3. **Test delivery and tracking**
   - Navigate to /admin/deliveries
   - Advance a partially fulfilled request's delivery to 'In Transit' then 'Delivered'
   - Verify request status changes to 'Partially Fulfilled'
   - Verify total_received is updated

4. **Test outstanding demand dashboard**
   - Navigate to /admin/outstanding
   - Verify partially fulfilled requests appear with progress bars
   - Verify remaining demand calculations are correct
   - Check admin dashboard shows outstanding demand count

5. **Test reallocation workflow**
   - Go to /admin/inventory
   - Receive new stock (e.g., 100 units of Drinking Water)
   - Click 'Reallocate Outstanding Demand' button
   - Verify allocation page shows both new pending requests and partially fulfilled requests
   - Apply allocation
   - Advance second delivery to 'Delivered'
   - Verify request status changes to 'Fulfilled' when remaining demand reaches 0

6. **Test user view**
   - Login as relief user (riverside@ngo.org / relief123)
   - View /my/requests
   - Verify progress indicators show received quantities and percentages
   - Verify multi-delivery requests show cumulative received amounts

## Implementation Order Rationale

- FEAT-001 first because database schema is the foundation for all other features
- FEAT-002 second because the algorithm must work with new schema before building UI
- FEAT-003 third to add visibility/dashboards for the working system
- FEAT-004 last to complete the workflow loop with reallocation buttons and multi-delivery polish

Each feature leaves the codebase in a working state and can be tested independently.
