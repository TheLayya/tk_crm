# TkCRM repository instructions

For requests to package, push a release, publish updates, add Windows assets, or change update/release tooling, read [.agents/skills/tk-crm-release/SKILL.md](.agents/skills/tk-crm-release/SKILL.md) and the relevant references. Keep that skill and the tested publishing scripts current when this module changes.

Team server upgrades are initiated by the user in the webpage. Publishing a GitHub release does not authorize calling team apply, SSH restarts/rebuilds or replacing server source. Preserve runtime data, environment files, user archives and backups; stage only selected source/documentation files.
