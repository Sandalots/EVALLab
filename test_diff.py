import csv

# Read the baseline
with open('papers/codebases/TextAttack/baseline/log.csv', 'r') as f:
    baseline_rows = list(csv.DictReader(f))

# Read the current
with open('papers/codebases/TextAttack/log.csv', 'r') as f:
    reader = csv.DictReader(f)
    rows = list(reader)
    fieldnames = reader.fieldnames

# Show current value
print(f"Baseline first row original_output: {baseline_rows[0]['original_output']}")
print(f"Current first row original_output: {rows[0]['original_output']}")

# Modify the first row's original_output to create a mismatch
rows[0]['original_output'] = '0'  # Change from '1' to '0'
print(f"\nChanged to: {rows[0]['original_output']}")

# Write back
with open('papers/codebases/TextAttack/log.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print("✓ Modified log.csv")
