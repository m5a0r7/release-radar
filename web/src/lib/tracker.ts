export type TrackerKind = 'jira' | 'github'

/** Short product name for links and labels: "open in Jira", "View in GitHub". */
export function trackerName(tracker: string): string {
  return tracker === 'github' ? 'GitHub' : 'Jira'
}

/** "Jira · KAFKA" or "GitHub Issues · apache/arrow". */
export function trackerLabel(tracker: string, key: string): string {
  return `${tracker === 'github' ? 'GitHub Issues' : 'Jira'} · ${key}`
}
