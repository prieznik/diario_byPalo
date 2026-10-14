"""Set the Status field of issues on a user-owned GitHub Project (v2).

Reads its inputs from environment variables so values typed into the workflow
form are never interpolated into shell commands.

  PROJECT_TOKEN   classic PAT with the `project` scope (from a repo secret)
  PROJECT_OWNER   user that owns the project, e.g. "prieznik"
  PROJECT_NUMBER  project number from its URL, e.g. 2
  REPO            "owner/name" of the repository that holds the issues
  ISSUES          comma- or space-separated issue numbers, e.g. "1, 9, 18"
  STATUS          name of the Status option, e.g. "Ready" (case-insensitive)
"""
import json
import os
import re
import sys
import urllib.request

API = "https://api.github.com/graphql"


def gql(query, **variables):
    req = urllib.request.Request(
        API,
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['PROJECT_TOKEN']}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        body = json.load(resp)
    if body.get("errors"):
        sys.exit(f"GraphQL error: {body['errors']}")
    return body["data"]


def main():
    owner = os.environ["PROJECT_OWNER"]
    number = int(os.environ["PROJECT_NUMBER"])
    repo_owner, repo_name = os.environ["REPO"].split("/")
    status = os.environ["STATUS"].strip()
    issues = [int(n) for n in re.findall(r"\d+", os.environ["ISSUES"])]
    if not issues:
        sys.exit("No issue numbers given.")

    project = gql(
        """query($owner:String!, $number:Int!) {
             user(login:$owner) { projectV2(number:$number) {
               id title
               field(name:"Status") { ... on ProjectV2SingleSelectField { id options { id name } } }
             } } }""",
        owner=owner, number=number,
    )["user"]["projectV2"]
    field = project["field"]
    options = {o["name"].lower(): o["id"] for o in field["options"]}
    if status.lower() not in options:
        sys.exit(f"Unknown status '{status}'. Available: {', '.join(o['name'] for o in field['options'])}")
    option_id = options[status.lower()]

    for n in issues:
        issue = gql(
            """query($o:String!, $r:String!, $n:Int!) {
                 repository(owner:$o, name:$r) { issue(number:$n) {
                   id title projectItems(first:50) { nodes { id project { id } } }
                 } } }""",
            o=repo_owner, r=repo_name, n=n,
        )["repository"]["issue"]
        if issue is None:
            print(f"#{n}: not found, skipped")
            continue
        item_id = next((i["id"] for i in issue["projectItems"]["nodes"]
                        if i["project"]["id"] == project["id"]), None)
        if item_id is None:
            item_id = gql(
                """mutation($p:ID!, $c:ID!) {
                     addProjectV2ItemById(input:{projectId:$p, contentId:$c}) { item { id } } }""",
                p=project["id"], c=issue["id"],
            )["addProjectV2ItemById"]["item"]["id"]
        gql(
            """mutation($p:ID!, $i:ID!, $f:ID!, $o:String!) {
                 updateProjectV2ItemFieldValue(input:{projectId:$p, itemId:$i, fieldId:$f,
                   value:{singleSelectOptionId:$o}}) { projectV2Item { id } } }""",
            p=project["id"], i=item_id, f=field["id"], o=option_id,
        )
        print(f"#{n} {issue['title']} -> {status}")


if __name__ == "__main__":
    main()
