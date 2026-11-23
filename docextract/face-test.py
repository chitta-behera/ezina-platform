# import boto3

# client = boto3.client(
#     "rekognition",
#     region_name="us-east-1"
# )

# with open("pass.png", "rb") as f:
#     id_image = f.read()

# with open("4eb06f81-6aca-45ce-8bae-50e5de332090.jpg", "rb") as f:
#     selfie_image = f.read()

# response = client.compare_faces(
#     SourceImage={"Bytes": selfie_image},
#     TargetImage={"Bytes": id_image},
#     SimilarityThreshold=80
# )

# print(response)
# # for match in response["FaceMatches"]:
# #     print(match())
#     # print("Similarity:", match["Similarity"])


######

import asyncio
from ezina_id_verify import extract_name, match_face

async def main():
    id_img = open("docextract/voterid.jpg", "rb").read()      # your test ID
    selfie = open("docextract/sel.jpg", "rb").read()   # your test selfie
    # print(await extract_name("driving_licence", id_img))          # driving_licence, aadhaar, passport, pan, voter_id, use the right doc_type for your ID
    print(await match_face(id_img, selfie)) # driving, pancard, xxx voterid, passport, aadhaar

asyncio.run(main())