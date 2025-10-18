# Changelog

## Unreleased
### Removed
- Removed support for the legacy `service_volume` key from service definitions. Inventories must use the `service_volumes` array instead. Validation now surfaces a warning and failure when the deprecated key is detected.

### Documentation
- Updated infrastructure README to reflect the removal timeline for `service_volume`.
