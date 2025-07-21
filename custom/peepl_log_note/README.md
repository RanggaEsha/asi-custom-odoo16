# Partner Log Note Dashboard

## Purpose

This module provides a searchable dashboard (tree/list view) for managing all "Log note" entries (`mail.message`) related to `res.partner`. It is designed for users who leverage log notes to store historical data and need an efficient way to search, review, and manage them.

## Features

- Adds a smart button to the `res.partner` form view (before "Meetings") for quick access to the log note dashboard.
- Tree (list) view of all log notes for the selected partner.
- **Responsive/Real-time:** The list view auto-synchronizes—new log notes or changes appear automatically without needing to refresh the page.
- Search and filter by:
  - Author
  - Date
  - Content (full-text search)
- Quick actions:
  - Edit log note (if permitted)
  - Delete log note (if permitted)
- Add new log note directly from the dashboard.
- Batch actions (delete/export) for selected log notes.
- Shows if a log note has attachments, with download/view options.
- Access rights respected (users see only what they are allowed to).
- No menu entry—access is only via the smart button on the partner form.

## Technical Details

- Source model: `mail.message`
- Domain: `model='res.partner'`, `message_type='comment'`, `subtype_id` = "note"
- Inherits Odoo security and access rules.
- Designed for extensibility and performance.
- Uses Odoo’s bus or auto-refresh mechanism for real-time updates.

## Installation

1. Copy the module to your Odoo addons directory.
2. Update the app list and install the module.

## Usage

- Open any partner form.
- Click the "Log Notes" smart button (before "Meetings") to open the dashboard.
- Use the search bar and filters to find relevant log notes.
- New log notes or changes will appear automatically.
- Click on a row to view or edit the note.
- Use batch actions as needed.

---