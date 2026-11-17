"""Demo data for iothings (the iosuite_demo package): the Calloways' things. The house's rooms and the garage, labels, appliances,
electronics, the bikes and the car with what they cost, warranties (one ending soon), receipts as PDFs, drawn photos,
upkeep that falls due (the furnace filter, the car's service) and a maintenance log, one thing sold."""
import iosuite_demo as demo

from app import files, model, upkeep, users

PLACES = {"House": ["Kitchen", "Living room", "Office", "Laundry room", "Basement"], "Garage": ["Workbench", "Shelves"],
          "Bedrooms": ["Morgan and Riley", "Ava", "Theo"], "Yard": ["Shed"]}
LABELS = [("Appliance", "#1a73e8"), ("Electronics", "#8e44d6"), ("Tools", "#e8710a"), ("Sports", "#1e8e3e"),
          ("Furniture", "#b5452f"), ("Kids", "#e0426a"), ("Valuable", "#e8a100")]

THINGS = [
    # name, place, labels, people, fields, days since purchase, warranty years (None: none), color
    ("Refrigerator", "House / Kitchen", ["Appliance"], [], {"manufacturer": "Northfield", "modelNumber": "NF-RF2850", "serialNumber": "NF28-4471-0093",
     "purchasePrice": "1849.00", "purchaseFrom": "Home Supply Co.", "insured": 1}, 900, 5, "#0b8a9e"),
    ("Dishwasher", "House / Kitchen", ["Appliance"], [], {"manufacturer": "Clearwave", "modelNumber": "CW-450", "serialNumber": "CW450-88213",
     "purchasePrice": "729.00", "purchaseFrom": "Home Supply Co."}, 340, 1, "#5f6b7a"),
    ("Washing machine", "House / Laundry room", ["Appliance"], [], {"manufacturer": "Clearwave", "modelNumber": "CW-W800", "serialNumber": "W800-11930",
     "purchasePrice": "899.00", "purchaseFrom": "Home Supply Co."}, 1500, 3, "#1a73e8"),
    ("Furnace", "House / Basement", ["Appliance"], [], {"manufacturer": "Thermaline", "modelNumber": "TL-96 Gas", "serialNumber": "TL96-2201-77",
     "purchasePrice": "4200.00", "purchaseFrom": "Alvarez Plumbing & Heating", "insured": 1,
     "notes": "Filter size 16x25x1. Service every autumn."}, 2200, 10, "#b5452f"),
    ("Living room TV", "House / Living room", ["Electronics", "Valuable"], [], {"manufacturer": "Visionix", "modelNumber": "VX-65Q",
     "serialNumber": "VX65Q-3390211", "purchasePrice": "1099.00", "purchaseFrom": "ElectroMart", "insured": 1}, 600, 2, "#4b53c7"),
    ("Laptop (Morgan)", "House / Office", ["Electronics", "Valuable"], ["morgan"], {"manufacturer": "Lumen", "modelNumber": "Lumen Pro 14",
     "serialNumber": "LP14-X7Q2-91", "purchasePrice": "1999.00", "purchaseFrom": "ElectroMart", "insured": 1,
     "fields": [{"name": "RAM", "value": "32 GB"}, {"name": "Storage", "value": "1 TB"}]}, 320, 1, "#1a73e8"),
    ("Tablet (Ava)", "Bedrooms / Ava", ["Electronics", "Kids"], ["ava"], {"manufacturer": "Lumen", "modelNumber": "Lumen Tab 11",
     "serialNumber": "LT11-55K0", "purchasePrice": "449.00", "purchaseFrom": "ElectroMart"}, 200, 1, "#e0426a"),
    ("Piano", "House / Living room", ["Furniture", "Valuable"], ["ava"], {"manufacturer": "Hartwell", "modelNumber": "Upright U1",
     "serialNumber": "H-118204", "purchasePrice": "3200.00", "purchaseFrom": "Harmony Music School (used)", "insured": 1,
     "notes": "Tune once a year."}, 1200, None, "#5f6b7a"),
    ("Mountain bike (Riley)", "Garage / Shelves", ["Sports"], ["riley"], {"manufacturer": "Ridgeback", "modelNumber": "Trail 29",
     "serialNumber": "RB29-7781", "purchasePrice": "1150.00", "purchaseFrom": "Spoke & Pedal"}, 700, 2, "#1e8e3e"),
    ("Kids' bike (Theo)", "Garage / Shelves", ["Sports", "Kids"], ["theo"], {"manufacturer": "Ridgeback", "modelNumber": "Sprout 20",
     "purchasePrice": "289.00", "purchaseFrom": "Spoke & Pedal"}, 400, 1, "#e8710a"),
    ("Cordless drill", "Garage / Workbench", ["Tools"], ["riley"], {"manufacturer": "ToughHand", "modelNumber": "TH-18V",
     "serialNumber": "TH18-02931", "purchasePrice": "149.00", "purchaseFrom": "Home Supply Co.", "lifetimeWarranty": 1}, 1000, None, "#e8a100"),
    ("Lawn mower", "Yard / Shed", ["Tools"], ["riley"], {"manufacturer": "GreenCut", "modelNumber": "GC-21 Electric",
     "purchasePrice": "399.00", "purchaseFrom": "Home Supply Co."}, 760, 3, "#1e8e3e"),
    ("Family car", None, ["Valuable"], ["morgan", "riley"], {"manufacturer": "Aurora Motors", "modelNumber": "Wayfarer Hybrid",
     "serialNumber": "VIN AUR5WF1H7PX010203", "purchasePrice": "32500.00", "purchaseFrom": "Juniper Auto", "insured": 1,
     "fields": [{"name": "Plate", "value": "DEMO 042"}, {"name": "Tyres", "value": "225/60 R17"}]}, 1100, 8, "#5f6b7a"),
    ("Telescope", "Bedrooms / Theo", ["Kids"], ["theo"], {"manufacturer": "StarPeek", "modelNumber": "SP-70",
     "purchasePrice": "129.00", "purchaseFrom": "Science Corner"}, 30, 1, "#4b53c7"),
]


def _receipt(name: str, price: str, shop: str, when) -> bytes:
    from fpdf import FPDF
    pdf = FPDF(format=(148, 210))
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, shop, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, f"Receipt  -  {when.isoformat()}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.cell(100, 8, name)
    pdf.cell(0, 8, f"${price}", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(100, 8, "Total")
    pdf.cell(0, 8, f"${price}", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(0, 6, "Demo receipt: made up for the ioSuite demo.")
    return bytes(pdf.output())


def seed(people: dict) -> None:
    m = users.get(people["morgan"]["id"])
    r = users.get(people["riley"]["id"])
    model.set_settings({"currency": "USD"})
    for parent, rooms in PLACES.items():
        pid = model.save_location(m, {"name": parent})["id"]
        for room in rooms:
            model.save_location(m, {"name": room, "parentId": pid})
    for name, color in LABELS:
        model.save_label(m, {"name": name, "color": color})

    made = {}
    for name, place, labels, who, fields, days, years, color in THINGS:
        bought = demo.day(-days)
        data = {"name": name, "location": place, "labels": labels, "people": [people[k]["id"] for k in who],
                "purchaseDate": bought.isoformat(), **fields}
        if years:
            data["warrantyExpires"] = bought.replace(year=bought.year + years).isoformat() if not (bought.month == 2 and bought.day == 29) else None
        it = model.create(m, data)
        made[name] = it
        files.add(m, it, demo.picture(name.split(" (")[0], color, (1000, 750)), f"{name}.jpg", "image/jpeg", "photo")
        if fields.get("purchasePrice") and days < 1300:
            files.add(m, it, _receipt(name, fields["purchasePrice"], fields.get("purchaseFrom") or "Shop", bought),
                      f"Receipt {name}.pdf", "application/pdf", "receipt")

    # the dishwasher's warranty ends in three weeks: the "ending soon" list has something
    model.update(m, made["Dishwasher"], {"warrantyExpires": demo.day(21).isoformat()})
    old = model.create(m, {"name": "Old sofa", "location": "House / Living room", "labels": ["Furniture"],
                           "purchaseDate": demo.day(-3000).isoformat(), "purchasePrice": "850.00", "archived": 1,
                           "soldDate": demo.day(-120).isoformat(), "soldPrice": "150.00", "soldTo": "Neighbour (Oliver Grant)"})
    files.add(m, old, demo.picture("Old sofa", "#b5452f", (1000, 750)), "Old sofa.jpg", "image/jpeg", "photo")

    for thing, title, n, unit, due, notes in [
        ("Furnace", "Replace the filter", 3, "month", demo.day(12), "16x25x1, in the basement cupboard"),
        ("Furnace", "Annual service", 1, "year", demo.day(-4), "Alvarez Plumbing & Heating"),
        ("Family car", "Service", 1, "year", demo.day(25), "Juniper Auto"),
        ("Family car", "Rotate the tyres", 6, "month", demo.day(60), None),
        ("Piano", "Tuning", 1, "year", demo.day(45), None),
        ("Lawn mower", "Sharpen the blade", 1, "year", demo.day(150), None),
        ("Refrigerator", "Clean the coils", 6, "month", demo.day(8), None),
    ]:
        upkeep.add(None, r, made[thing]["id"], {"title": title, "everyN": n, "everyUnit": unit, "nextDue": due.isoformat(), "notes": notes})
    for thing, days, title, cost, by in [
        ("Furnace", -369, "Annual service", "129.00", "Alvarez Plumbing & Heating"),
        ("Furnace", -80, "Replaced the filter", "18.50", "Riley"),
        ("Family car", -340, "Service and oil change", "289.00", "Juniper Auto"),
        ("Family car", -160, "New wiper blades", "34.00", "Riley"),
        ("Washing machine", -200, "Replaced the drain pump", "95.00", "Tony Alvarez"),
        ("Piano", -320, "Tuning", "140.00", "Harmony Music School"),
    ]:
        upkeep.log_add(r, made[thing]["id"], {"date": demo.day(days).isoformat(), "title": title, "cost": cost, "doneBy": by})
