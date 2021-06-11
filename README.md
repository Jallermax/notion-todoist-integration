Run to start workflow of creating history records to Notion for each completed Todoist task linked with Notion (Maintenance action DB) and creating new linked Todoist tasks for each maintenance action without one. Single run only for now, periodical job runs later.

**Technical TODO:**
* Setup CI/DI + project structure improvement
* Add delay for jobs start
* Limit completed tasks query by time (1-7 day before now)
* Fix timezones (Todoist completed date -> Notion history completed)
* Improve logging of each api call (log all params) and on logic workflow
* Refactor workflow for better readability (for reuse and GUI later)
* Decouple notion module as separate lib
* Increase robustness (check for changes in DB namings, imply possibility of manual changing task id or deleting task,
  rollback on errors in workflow)

**Feature plan:**</br>
* Save task comments to notion history
* Add global tag system (to interconnect tasks in todoist with maintenance mindset and with influence on wheel of well-being)
* Webhook triggers (run on notion page update?)
* Add explicit error notification (to tg bot for example)
* Think about workflow with repeatable tasks (any pros except better visibility in todoist?)
* See list and statuses of all scenarios/workflows, enable/disable without app restart
---
**Gui (long term plan)**
* GUI for visualizing job schedule and status
* GUI for visualizing workflows
* GUI for constructing workflows (zapier, automate.io etc.)

---
*Links:*</br>
[Notion template for Maintenance Actions DB](https://www.notion.so/Maintenance-Actions-60655507245548fb8393f8a7499c251c) </br>
[Todoist API](https://developer.todoist.com/sync/) </br>
[Notion API](https://developers.notion.com/reference) </br>
