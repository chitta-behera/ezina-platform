import re
import sys
import boto3


def extract_name_from_mrz(lines: list[str]) -> dict | None:
    """Find the passport MRZ name line (starts with 'P<') and return the name parts."""
    for raw in lines:
        line = raw.replace(" ", "").upper().replace("«", "<<")  # common OCR slips
        if not line.startswith("P<") or "<<" not in line:
            continue
        names = line[5:]                      # skip 'P<' + 3-letter country code
        surname, _, given = names.partition("<<")
        surname = surname.replace("<", " ").strip()
        given = re.sub(r"<+", " ", given).strip()
        if surname or given:
            return {
                "surname": surname,
                "given_names": given,
                "full_name": f"{given} {surname}".strip(),
            }
    return None


def main(image_path: str) -> None:
    # Create the Rekognition client (uses your AWS keys from `aws configure` or env vars)
    client = boto3.client("rekognition", region_name="us-east-1")

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    resp = client.detect_text(Image={"Bytes": image_bytes})

    # Use LINE detections (whole lines), not WORD
    lines = [d["DetectedText"] for d in resp["TextDetections"] if d["Type"] == "LINE"]

    result = extract_name_from_mrz(lines)
    if result:
        print("Name found:", result)
    else:
        print("No MRZ name line found. Detected lines:")
        for line in lines:
            print("  ", line)


if __name__ == "__main__":
    main("pass.png")