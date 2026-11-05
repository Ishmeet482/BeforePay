export default function TechnicalDetails({ label = 'Version details', data }: { label?: string; data: Record<string, unknown> }) {
  return <details className="technical-details"><summary>{label}</summary><pre>{JSON.stringify(data, null, 2)}</pre></details>
}
