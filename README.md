**Technical TODO:**</br>
* Setup CI/DI + project structure improvement</br>
* Add delay for jobs start</br>
* Limit completed tasks query by time (1-7 day before now)</br>
* Fix timezones (Todoist completed date -> Notion history completed)</br>
* Refactor workflow for better readability (for reuse and GUI later)</br>
* Decouple notion module as separate lib</br>
* Increase robustness (check for changes in DB namings, imply possibility of manual changing task id or deleting task)</br>

**Feature plan:**</br>
* Save task comments to notion history</br>
* Add global tag system (to interconnect tasks in todoist with maintenance mindset and with influence on wheel of well-being)</br>
* Add explicit error notification (to tg bot for example)</br>
* Think about workflow with repeatable tasks (any pros except better visibility in todoist?)</br>
---
**Gui (long term plan)**
* GUI for visualizing job schedule and status
* GUI for visualizing workflows
* GUI for constructing workflows (zapier, automate.io etc.)

---
*Links:*
https://developer.todoist.com/sync/
https://developers.notion.com/reference </br>
TODO: Notion template for Maintenance Actions DB