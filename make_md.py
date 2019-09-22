import re

with open("README.md") as infile:
    text = infile.read()

# Make links work in github
text = re.sub(
    r"\]\(#(.+?)\)",
    lambda m: "](#" +
              m.group(1)
                  .lower()
                  .replace('/', '')
              + ")",
    text,
)

with open("README.md", "w") as outfile:
    outfile.write(text)
