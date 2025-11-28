def extract_per_example_from_logcsv(log_csv_path):
    """Extract per-example results from a TextAttack log.csv file."""
    import csv
    results = []
    with open(log_csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            results.append(dict(row))
    return results
