import urllib.parse

password = "jksahf nbyer 93qr%@#%fafr32453f"
encoded_password = urllib.parse.quote_plus(password)
print(encoded_password)  # Output: jksahf+nbyer+93qr%25%40%23%25fafr32453f