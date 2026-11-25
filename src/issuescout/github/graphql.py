"""GraphQL queries for GitHub API."""

SEARCH_MERGED_PRS = """
query SearchMergedPRs($query: String!, $first: Int!, $after: String) {
  search(query: $query, type: ISSUE, first: $first, after: $after) {
    issueCount
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      ... on PullRequest {
        number
        title
        body
        state
        merged
        mergeable
        createdAt
        updatedAt
        closedAt
        mergedAt
        baseRefOid
        headRefOid
        baseRefName
        headRefName
        url
        closingIssuesReferences(first: 10) {
          nodes {
            number
          }
        }
      }
    }
  }
}
"""

GET_ISSUE = """
query GetIssue($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    issue(number: $number) {
      number
      title
      body
      createdAt
      updatedAt
      closedAt
      state
      url
    }
  }
}
"""

GET_PR_FILES = """
query GetPRFiles($owner: String!, $repo: String!, $number: Int!, $first: Int!, $after: String) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      files(first: $first, after: $after) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          path
          additions
          deletions
          viewerDidAuthor
        }
      }
    }
  }
}
"""

RATE_LIMIT_QUERY = """
query RateLimit {
  rateLimit {
    limit
    remaining
    resetAt
    used
  }
}
"""