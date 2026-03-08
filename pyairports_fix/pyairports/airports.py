"""Airport data for outlines compatibility."""

# Format: (name, city, country, iata_code, icao_code, lat, lon, alt, timezone, dst, tz_name)
# Index 3 = IATA code (outlines가 airport[3]로 접근)
AIRPORT_LIST = [
    ("Incheon International Airport", "Seoul", "South Korea", "ICN", "RKSI", "37.469", "126.451", "23", "9", "U", "Asia/Seoul"),
    ("Gimpo International Airport", "Seoul", "South Korea", "GMP", "RKSS", "37.558", "126.791", "59", "9", "U", "Asia/Seoul"),
    ("John F. Kennedy International Airport", "New York", "United States", "JFK", "KJFK", "40.639", "-73.779", "13", "-5", "A", "America/New_York"),
    ("Los Angeles International Airport", "Los Angeles", "United States", "LAX", "KLAX", "33.942", "-118.408", "38", "-8", "A", "America/Los_Angeles"),
    ("London Heathrow Airport", "London", "United Kingdom", "LHR", "EGLL", "51.471", "-0.461", "83", "0", "E", "Europe/London"),
]
