Every 60 seconds runs workflow of creating history records to Notion for each completed Todoist task linked with
Notion (Maintenance action DB) and creating new linked Todoist tasks for each maintenance action without one.</br>

## Environment Setup

1. Copy the `.env.example` file to `.env` and fill in the required environment variables:
   ```bash
   cp .env.example .env
   ```
2. Customize mappings.json with your specific mappings between Todoist projects and Notion databases.
3. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

---
*Links:*</br>
[Notion template for Maintenance Actions DB](https://www.notion.so/Maintenance-Actions-60655507245548fb8393f8a7499c251c) </br>
[Todoist API](https://developer.todoist.com/sync/) </br>
[Notion API](https://developers.notion.com/reference) </br>
