**User Session Audit Module for Odoo 16 Enterprise**

This document outlines the design and implementation plan for the **User Session Audit** custom module in Odoo 16 Enterprise. It includes:

1. **New Models**
2. **Views**
3. **Data Relationships**
4. **Security (Groups, Access Rights, Record Rules)**
5. **Module Concept and Workflow**

---

## 1. New Models

| Model Name                     | Technical Name              | Purpose                                                                                             |
|--------------------------------|-----------------------------|-----------------------------------------------------------------------------------------------------|
| Audit Configuration            | `audit.config`              | Stores global audit settings (operations allowed, users/objects to audit).                           |
| Audit Configuration Users      | `audit.config.user`         | Lines to select specific users for auditing (many2one to res.users).                                |
| Audit Configuration Objects    | `audit.config.object`       | Lines to select specific models/objects for auditing.                                               |
| Audit Log Entry                | `audit.log.entry`           | Stores each audit event (create, write, read, unlink) with old/new values and session link.         |
| Audit Session                  | `audit.session`             | Tracks user login sessions (login_time, logout_time, device, geo, status).                          |
| Audit Log Clear Wizard         | `audit.clear.wizard`        | Wizard to clear audit logs based on filters (date, action type, object).                            |


## 2. Views

---

### Technical Breakdown & Implementation Notes

#### Audit Configuration (`audit.config`)
- **Technique:** Inherit from `models.Model`. Use boolean fields for operations, one2many for users/objects. Reference Odoo config models (`res.config.settings`).
- **Considerations:** Use computed fields for "All Users". Ensure access rights via `ir.model.access.csv`. Use `ir.model` for dynamic object selection.

#### Audit Configuration Users (`audit.config.user`)
- **Technique:** Many2one to `res.users`, Many2one to `audit.config`. Use Odoo relational fields.
- **Considerations:** Handle "All Users" logic in parent config. Use domain filters for user selection.

#### Audit Configuration Objects (`audit.config.object`)
- **Technique:** Many2one to `ir.model`, Many2one to `audit.config`. Use Odoo’s model registry for dynamic selection.
- **Considerations:** Restrict selectable models via domain. Reference technical settings for model listing.

#### Audit Log Entry (`audit.log.entry`)
- **Technique:** Store event details (user, session, object, record id, action type, date, changes). Use JSON/text fields for old/new values. Reference `mail.message`, `ir.logging`.
- **Considerations:** Use bus/event system or ORM overrides for logging. Ensure performance by filtering events.

#### Audit Session (`audit.session`)
- **Technique:** Track login/logout, device, geo, status. Hook into authentication (`Session.authenticate` in `http.py`). Use session object (`request.session`).
- **Considerations:** Capture device info from user agent, IP from `request.httprequest.remote_addr`. Update session record on logout.

#### Audit Log Clear Wizard (`audit.clear.wizard`)
- **Technique:** Use `models.TransientModel` for wizard. Implement wizard actions and filters. Reference core wizards for UI.
- **Considerations:** Restrict access to managers. Use ORM `unlink` with domain for log deletion.

---

### 2.1 Configuration Views

- **Audit Config Tree** (`audit.config.tree`)
  - Columns: Name, Read, Write, Create, Delete, All Users (boolean)
- **Audit Config Form** (`audit.config.form`)
  - Sections:
    - **Users Section**: One2many to `audit.config.user`, with boolean "All Users" toggle.
    - **Objects Section**: One2many to `audit.config.object`, listing models to audit.
    - Operation Booleans: Read, Write, Create, Delete.

### 2.2 Audit Logs Views

- **Audit Log Tree** (`audit.log.entry.tree`)
  - Columns: Reference (char), User, Session, Object, Record ID, Action Type, Date, New Changes, Old Changes.
- **Audit Log Form** (`audit.log.entry.form`)
  - Same fields in grouped layout for detail view.

### 2.3 Clear Logs Wizard View

- **Clear Audit Logs Wizard** (`audit.clear.wizard.form`)
  - Fields: Full Log (boolean), To Date (date), Read, Write, Create, Delete (booleans), Object (many2one to `ir.model`).

### 2.4 Session Logs Views

- **Session Log Tree** (`audit.session.tree`)
  - Columns: Status, User, Login Time, Logout Time, Session ID, IP Address, Device Name, Device Type, Error Message, Button "View Activity".
- **Session Log Form** (`audit.session.form`)
  - Detailed session info with One2many list of related `audit.log.entry` records.

---

## 3. Data Relationships

- `audit.config` 1––* `audit.config.user` (Many2one: config_id)
- `audit.config` 1––* `audit.config.object` (Many2one: config_id)
- `audit.log.entry` *––1 `res.users` (user_id)
- `audit.log.entry` *––1 `audit.session` (session_id)
- `audit.log.entry` *––1 `ir.model` (model_id)
- `audit.log.entry` *––1 target record via generic fields: `res_model` and `res_id`.
- `audit.session` *––1 `res.users` (user_id)

---

## 4. Security

### 4.1 Groups

- **Audit User** (`group_audit_user`)
  - Can view own sessions and logs.
  - Access to `audit.log.entry` tree/form filtered by owner.
  - Cannot clear logs.

- **Audit Manager** (`group_audit_manager`)
  - Full access to all logs, sessions, and configurations.
  - Can clear logs via wizard.

### 4.2 Access Rights

| Model                  | Audit User | Audit Manager | Technical Rights              |
|------------------------|------------|---------------|-------------------------------|
| `audit.config`         | None       | Full (CRUD)   | `audit.manager` only          |
| `audit.config.user`    | None       | Full (CRUD)   | `audit.manager` only          |
| `audit.config.object`  | None       | Full (CRUD)   | `audit.manager` only          |
| `audit.log.entry`      | Read Own   | Read All      | `audit.user` / `audit.manager`|
| `audit.session`        | Read Own   | Read All      | `audit.user` / `audit.manager`|
| `audit.clear.wizard`   | None       | Execute       | `audit.manager` only          |

### 4.3 Record Rules

- **audit_log_user_rule**: `['|', ('user_id','=',user.id), ('session_id.user_id','=',user.id)]` applied to `audit.log.entry` for `audit.user` group.
- **audit_session_user_rule**: `['|', ('user_id','=',user.id), ('id','in', session_ids_of_user)]` for `audit.session`.

---

## 5. Module Concept & Workflow

1. **Configuration**: Administrator creates an Audit Configuration record, selects operations to monitor, users (or selects All Users), and objects (models) to audit.
2. **Session Tracking**: On each user login, an `audit.session` record is created capturing IP, device, OS, and timestamp. On logout, the record is updated.
3. **Action Logging**: A global model override or `bus` event logs each `create`, `read`, `write`, and `unlink` for selected models and users, creating `audit.log.entry` entries linked to the active session.
4. **Viewing Logs**: Users open the **Session Logs** to see their own sessions and click **View Activity** to inspect related log entries. Managers see all.
5. **Clearing Logs**: Managers use the Clear Logs Wizard to purge logs by date or action type.



Technical Breakdown & Implementation Notes
Configuration: Use onchange methods and computed fields to handle "All Users" logic and dynamic object selection.
Session Tracking: Hook into Odoo’s authentication flow (Session.authenticate and Session.logout in http.py). Capture session info from request object.
Action Logging: Override model methods (create, write, unlink, read) for selected models. Use Odoo’s bus/event system or model inheritance for logging.
Log Linkage: Link each log entry to the active session using request.session.sid.
Viewing Logs: Use domain filters and smart buttons for user/manager views. Reference core log and activity views.
Clearing Logs: Implement wizard logic to filter and delete logs using ORM unlink and domain expressions.


---

**Prepared by:** Odoo 16 Enterprise Customization Team

**Date:** July 22, 2025

