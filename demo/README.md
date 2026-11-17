# ioSuite demo data

The `iosuite_demo` package: a made-up family of four, the Calloways, with something in every app of the suite. It is
never installed with an app (installs and Docker images carry only an app's own folder and `shared/`): while the suite's
demo switch is on (`iosuite-shared demo`, or the compose builder's "Fill it with demo data"), an app that starts and has
not been seeded fetches this package and runs its module from it (`iosuite_shared.demo.at_start`). The release workflow
attaches it to every suite release as `iosuite-demo.zip`; a git checkout uses this folder.

- `iosuite_demo/__init__.py`: the family, their accounts (`ensure`), `run`/`seed`, drawn pictures.
- `iosuite_demo/<app>.py`: each app's `seed(people)`, written with that app's own code (`from app import ...`).
- `iosuite_demo/recipes/`: the photos of the demo recipes (Wikimedia Commons, credited in `credits.json`).
- ioPix's photos are a separate download (`iopix-demo-photos.zip` on the `demo-photos-1` release, credits inside).

Each app's `tests/test_demo.py` runs its seed against a fresh database. See the docs: Getting started › Demo data.
