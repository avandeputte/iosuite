"""ioContacts: self-hosted contacts for the iothing suite."""
__version__ = "0.8.0"

# the settings load first: they point iosuite-shared at the Shared ioSuite database before any module imports it
__import__("app.config")
