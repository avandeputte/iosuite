"""Demo data for iostart (the iosuite_demo package): the Calloways' start page. Shared bookmark folders everyone sees (Family, School,
Home), and each person's own: Morgan's work links, Riley's teaching links, Ava's and Theo's. The web addresses are
public sites, not anyone's account."""
from iosuite_shared import users as shared_users

from app import bookmarks

SHARED = {
    "Family": [("Weather", "https://www.weather.gov/"), ("Maps", "https://www.openstreetmap.org/"),
               ("Library", "https://openlibrary.org/"), ("Recipes", "https://www.allrecipes.com/")],
    "School": [("Khan Academy", "https://www.khanacademy.org/"), ("Scratch", "https://scratch.mit.edu/"),
               ("Wikipedia", "https://en.wikipedia.org/"), ("Duolingo", "https://www.duolingo.com/")],
    "Home": [("Energy saving tips", "https://www.energy.gov/energysaver/energy-saver"),
             ("Recycling guide", "https://www.epa.gov/recycle"), ("Gardening", "https://www.rhs.org.uk/advice")],
}
OWN = {
    "morgan": {"Work": [("Landscape Architecture Magazine", "https://landscapearchitecturemagazine.org/"),
                        ("Native plants", "https://www.wildflower.org/plants/"), ("OpenStreetMap", "https://www.openstreetmap.org/")],
               "Running": [("Strava", "https://www.strava.com/"), ("Race calendar", "https://runsignup.com/")]},
    "riley": {"Teaching": [("PhET simulations", "https://phet.colorado.edu/"), ("Periodic table", "https://ptable.com/"),
                           ("Chemistry LibreTexts", "https://chem.libretexts.org/")],
              "Cycling": [("Bike routes", "https://www.ridewithgps.com/")]},
    "ava": {"Piano": [("Musescore", "https://musescore.com/"), ("Metronome", "https://www.metronomeonline.com/")],
            "Science fair": [("Science Buddies", "https://www.sciencebuddies.org/")]},
    "theo": {"Fun": [("NASA Kids Club", "https://www.nasa.gov/kidsclub/"), ("National Geographic Kids", "https://kids.nationalgeographic.com/")]},
}


def seed(people: dict) -> None:
    morgan = shared_users.get(people["morgan"]["id"], "iostart")
    bookmarks.as_user(morgan)
    for folder, links in SHARED.items():
        f = bookmarks.create(None, True, folder, start=True)
        bookmarks.change(f["id"], {"shared": True})
        for name, url in links:
            bookmarks.create(f["id"], False, name, url)
    for key, folders in OWN.items():
        bookmarks.as_user(shared_users.get(people[key]["id"], "iostart"))
        for folder, links in folders.items():
            f = bookmarks.create(None, True, folder, start=True)
            for name, url in links:
                bookmarks.create(f["id"], False, name, url)
    bookmarks._viewer.set(None)
