# CRM Activity Dashboard

A comprehensive Odoo 16 module that provides an advanced dashboard for managing and tracking CRM activities with enhanced filtering, color-coding, and detailed analytics.

## 🚀 Features

### 📊 Comprehensive Dashboard
- **Complete Activity Overview**: View all mail activities from CRM leads and opportunities in one centralized location
- **Real-time Data**: Automatically updates to reflect the current state of activities
- **Multiple Views**: List, Kanban, Calendar, Pivot, and Graph views for different perspectives

### 🎨 Color-Coded Status System
- **Red**: Overdue activities (with darker red for activities overdue more than 7 days)
- **Orange**: Activities due today
- **Yellow**: Activities due tomorrow  
- **Grey**: Planned future activities
- **Green**: Completed activities

### 🔍 Advanced Filtering
#### Time-based Filters
- Today, Tomorrow, Yesterday
- This Week, Past Week
- This Month, Past Month
- This Year, Past Year

#### Status Filters
- Overdue, Today, Tomorrow, Planned, Done
- My Activities (assigned to current user)
- High Priority activities

#### Business Filters
- Leads vs Opportunities
- By Sales Team
- By Activity Type
- By Customer
- By Stage

### 👥 Access Control
- **Dashboard User Group**: View-only access to activity dashboard
- **Dashboard Manager Group**: Full access including edit and management capabilities
- **Security Rules**: Ensures users only see activities they have permission to view

### 📈 Analytics & Reporting
- **Pivot Tables**: Analyze activities by user, team, status, and time periods
- **Graphs**: Visual representation of activity distribution and trends
- **Calendar View**: Timeline view of scheduled activities
- **Kanban Boards**: Organized by status with drag-and-drop functionality

### ⚡ Quick Actions
- Mark activities as done
- Schedule next activities
- Open related leads/opportunities
- Edit activity details
- Bulk operations for managers

## 🛠️ Installation

1. Copy the module to your custom addons directory:
   ```bash
   cp -r dashboard_crm_activity /path/to/odoo/custom/addons/
   ```

2. Update the addons list:
   ```bash
   ./odoo-bin -u all -d your_database
   ```

3. Install the module through Odoo Apps interface or command line:
   ```bash
   ./odoo-bin -i dashboard_crm_activity -d your_database
   ```

## 📋 Requirements

- Odoo 16.0+
- CRM module (automatic dependency)
- Mail module (automatic dependency)

## 🎯 Usage

### Accessing the Dashboard
1. Navigate to **CRM → Activity Dashboard**
2. Use the search filters to find specific activities
3. Switch between different views using the view selector

### Setting Up Access Rights
1. Go to **Settings → Users & Companies → Groups**
2. Add users to either:
   - **CRM Activity Dashboard User**: View-only access
   - **CRM Activity Dashboard Manager**: Full access

### Customizing Filters
- Use the search bar to find specific activities
- Apply multiple filters simultaneously
- Save frequently used filter combinations
- Group activities by different criteria

### Working with Activities
- **View Details**: Click on any activity to see full details
- **Quick Actions**: Use toolbar buttons for common operations
- **Bulk Operations**: Select multiple activities for batch processing
- **Calendar View**: Schedule and visualize activity timelines

## 🔧 Configuration

### Color Customization
The color scheme can be customized by modifying the `_compute_activity_color` method in the model or by updating the CSS in `views/assets.xml`.

### Adding Custom Filters
New filters can be added by extending the search view in `views/crm_activity_dashboard_views.xml`.

### Priority Mapping
Activity priority is automatically computed based on activity type names. This can be customized in the `_compute_priority` method.

## 📊 Database Views

The module creates a SQL view that combines data from:
- `mail.activity` (activity details)
- `crm.lead` (lead/opportunity information)
- Related models (users, teams, stages, etc.)

The view automatically refreshes when activities are created, updated, or deleted.

## 🔄 Automatic Updates

- **Hourly Refresh**: Scheduled action refreshes the dashboard view every hour
- **Real-time Updates**: Changes to activities immediately update the dashboard
- **Cache Management**: Efficient caching ensures optimal performance

## 🎨 User Interface

### List View Features
- Color-coded rows based on activity status
- Sortable columns
- Expandable details
- Action buttons for quick operations

### Kanban View Features
- Status-based columns
- Color-coded cards
- Priority indicators
- User avatars
- Revenue information

### Calendar View Features
- Monthly, weekly, and daily views
- Color coding by assigned user
- Drag-and-drop rescheduling
- Activity type icons

## 🚀 Performance

- Optimized SQL views for fast data retrieval
- Efficient indexing on key fields
- Minimal server-side processing
- Client-side caching for improved responsiveness

## 🛡️ Security

- Row-level security ensures users only see authorized data
- Group-based access control
- Audit trail for all activities
- Secure API endpoints

## 📞 Support

For issues, feature requests, or customizations, please contact the development team or create an issue in the project repository.

## 📄 License

This module is provided under the LGPL-3 license. See LICENSE file for details.

## 🔄 Changelog

### Version 1.0.0
- Initial release
- Complete dashboard functionality
- Color-coded status system
- Advanced filtering options
- Multiple view types
- Access control implementation
- Performance optimizations

---

**Author**: ASI Custom Development  
**Version**: 1.0.0  
**Odoo Version**: 16.0+  
**Category**: CRM
