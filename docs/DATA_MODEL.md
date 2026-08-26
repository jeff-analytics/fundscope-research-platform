# Data Model

Recommended production entities:

- fund_master
- fund_share_class
- manager
- manager_tenure
- report
- holding
- security_master
- market_consensus
- industry_allocation
- task_health

Current v1 local implementation retains compatibility with the earlier FundScope SQLite schema while exposing a cleaner API layer.
