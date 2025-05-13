import dns.resolver

hostname = "db.hilpkmebnaqzadkyphtr.supabase.co"
print(f"Attempting to resolve hostname: {hostname} using Google DNS (8.8.8.8)")

my_resolver = dns.resolver.Resolver()
my_resolver.nameservers = ['8.8.8.8']
found_address = False

try:
    print(f"Querying A records (IPv4) for {hostname}...")
    a_records = my_resolver.resolve(hostname, 'A')
    for rdata in a_records:
        print(f"  IPv4 Address (A): {rdata.address}")
        found_address = True
except dns.resolver.NoAnswer:
    print(f"  No A records (IPv4) found.")
except dns.resolver.NXDOMAIN:
    print(f"  DNS Resolution Error (NXDOMAIN) for '{hostname}' A records: The domain does not exist.")
except Exception as e:
    print(f"  Error querying A records: {e}")

try:
    print(f"Querying AAAA records (IPv6) for {hostname}...")
    aaaa_records = my_resolver.resolve(hostname, 'AAAA')
    for rdata in aaaa_records:
        print(f"  IPv6 Address (AAAA): {rdata.address}")
        found_address = True
except dns.resolver.NoAnswer:
    print(f"  No AAAA records (IPv6) found.")
except dns.resolver.NXDOMAIN:
    print(f"  DNS Resolution Error (NXDOMAIN) for '{hostname}' AAAA records: The domain does not exist.")
except Exception as e:
    print(f"  Error querying AAAA records: {e}")

if found_address:
    print("DNS resolution with dnspython successful (found at least one type of record).")
else:
    print("DNS resolution with dnspython FAILED (found no A or AAAA records via Google DNS).")