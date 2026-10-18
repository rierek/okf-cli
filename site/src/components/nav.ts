// Header navigation (usememos.com style). Groups with `items` become drop-downs with a one-line description per
// entry. Hrefs are site-relative and must match page slugs in wiki (chapters: see sidebar in astro.config.mjs).
// "Resources" lists Releases, Known limitations, Contribute and About; the sidebar chapter "Resources" holds the same.
export interface NavItem {
	title: string;
	description: string;
	href: string;
}
export type NavEntry = { label: string; href: string } | { label: string; items: NavItem[] };

export const nav: NavEntry[] = [
	{
		label: 'Overview',
		items: [
			{ title: 'okf in brief', description: 'What okf is and where to go next', href: '/overview/' },
			{ title: 'Installation', description: 'Install the okf binary', href: '/overview/installation/' },
			{ title: 'First steps', description: 'Point okf at a catalogue and run your first commands', href: '/overview/first-steps/' },
			{ title: 'Concepts', description: 'Catalogues, bundles, concepts and types', href: '/overview/concepts/' },
			{ title: 'Agent onboarding', description: 'Teach a coding agent to use okf', href: '/overview/agent-onboarding/' },
			{ title: 'Upgrading', description: 'Move from the Python CLI to the Go binary', href: '/overview/upgrading/' },
			{ title: 'Troubleshooting', description: 'Symptom-first fixes for common problems', href: '/overview/troubleshooting/' },
		],
	},
	{
		label: 'Features',
		items: [
			{ title: 'All features', description: 'Everything okf does, at a glance', href: '/features/' },
			{ title: 'Search', description: 'Ranked search narrowed by a where filter', href: '/features/search/' },
			{ title: 'Context bundles', description: 'Curated reading lists for sessions', href: '/features/context-bundles/' },
			{ title: 'Conformance checks', description: 'Scan a catalogue against the format rules', href: '/features/conformance-checks/' },
			{ title: 'Safe edits', description: 'Preview first, then apply renames and rewrites', href: '/features/safe-edits/' },
			{ title: 'Tags and registry', description: 'Tag usage, fuzzy search and the tag registry', href: '/features/tags-and-registry/' },
			{ title: 'Canon blocks', description: 'Shared text kept in sync across concepts', href: '/features/canon-blocks/' },
		],
	},
	{
		label: 'Use Cases',
		items: [
			{ title: 'All use cases', description: 'Real problems, solved with okf', href: '/use-cases/' },
			{ title: 'Onboard an agent', description: 'Give a fresh session the catalogue map', href: '/use-cases/onboard-an-agent/' },
			{ title: 'Reorganise without broken links', description: 'Rename and move concepts safely', href: '/use-cases/reorganise-without-broken-links/' },
			{ title: 'Migrate to OKF 0.2', description: 'Bring a catalogue to the 0.2 format', href: '/use-cases/migrate-to-okf-0-2/' },
			{ title: 'Curate a reading bundle', description: 'Collect the pages a topic needs', href: '/use-cases/curate-a-reading-bundle/' },
		],
	},
	{ label: 'Reference', href: '/reference/' },
	{
		label: 'Resources',
		items: [
			{ title: 'Releases', description: 'What changed in each version', href: '/releases/' },
			{ title: 'Known limitations', description: 'Open defects, by short ID', href: '/known-limitations/' },
			{ title: 'Contribute', description: 'Report bugs, build from source', href: '/contribute/' },
			{ title: 'About', description: 'What okf is and where it comes from', href: '/about/' },
		],
	},
];
