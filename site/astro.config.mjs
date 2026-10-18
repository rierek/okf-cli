// Scaffold copied from the Lif docs site (site/ in the Lif repo); see docs/topics/okf-docs-site/ERPROBUNG.md.
// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import { fileURLToPath } from 'node:url';
import catppuccin from '@catppuccin/starlight';

export default defineConfig({
	vite: {
		plugins: [{
			// Content lives in ../wiki: resolve its bare imports from site/node_modules.
			name: 'wiki-resolve',
			enforce: 'pre',
			async resolveId(id, importer, opts) {
				if (!importer || !/[\\/]wiki[\\/]/.test(importer) || !/^(@astrojs|@lucide)\//.test(id)) return null;
				return this.resolve(id, fileURLToPath(new URL('./package.json', import.meta.url)), { ...opts, skipSelf: true });
			},
		}],
	},
	site: 'https://xrieros.github.io',
	base: '/okf-cli',
	integrations: [
		starlight({
			title: 'okf',
			description: 'CLI and MCP server for Open Knowledge Format (OKF) catalogues',
			components: { Header: './src/components/Header.astro' },
			customCss: ['./src/styles/custom.css', './src/styles/elements.css'],
			// Code blocks use the same Catppuccin flavours as the site. Expressive Code raises token
			// contrast against the theme base; the panes sit on mantle (--okf-surface), so the floor is above 4.5:1 with
			// room to spare. Options must stay serializable (a function here breaks the dev stylesheet route).
			expressiveCode: {
				themes: ['catppuccin-mocha', 'catppuccin-latte'],
				minSyntaxHighlightingColorContrast: 6.5,
				styleOverrides: {
					borderRadius: '0.5rem',
					borderWidth: '1px',
					codeFontSize: '0.875rem',
					codeLineHeight: '1.7',
					textMarkers: { lineMarkerAccentWidth: '0px', backgroundOpacity: '35%' },
				},
			},
			// D36/D51: sidebar mode (all chapters or current chapter only) is one switch in src/routeData.ts.
			routeMiddleware: './src/routeData.ts',
			// custom.css defines the --ctp-* tones for these two flavours; change both together.
			plugins: [catppuccin({ dark: { flavor: 'mocha', accent: 'blue' }, light: { flavor: 'latte', accent: 'blue' } })],
			social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/xRiErOS/okf-cli' }],
			// Each top-level group is a chapter. Header chapters: Overview, Features, Use Cases, Reference, Resources
			// (= Releases, Known limitations, Contribute, About); see src/components/nav.ts.
			sidebar: [
				{
					label: 'Overview',
					items: [
						'overview',
						'overview/installation',
						'overview/first-steps',
						'overview/concepts',
						'overview/agent-onboarding',
						'overview/upgrading',
						'overview/troubleshooting',
					],
				},
				{
					label: 'Features',
					items: [
						'features',
						'features/search',
						'features/context-bundles',
						'features/conformance-checks',
						'features/safe-edits',
						'features/tags-and-registry',
						'features/canon-blocks',
					],
				},
				{
					label: 'Use Cases',
					items: [
						'use-cases',
						'use-cases/onboard-an-agent',
						'use-cases/reorganise-without-broken-links',
						'use-cases/migrate-to-okf-0-2',
						'use-cases/curate-a-reading-bundle',
					],
				},
				{
					label: 'Reference',
					items: [
						'reference',
						{ label: 'Commands', items: [{ autogenerate: { directory: 'reference/commands' } }] },
						'reference/where-filter',
						'reference/json-output-and-exit-codes',
						'reference/configuration',
						'reference/frontmatter-and-types',
						'reference/glossary',
					],
				},
				{
					label: 'Resources',
					items: [{ label: 'Releases', items: [{ autogenerate: { directory: 'releases' } }] }, 'known-limitations', 'contribute', 'about'],
				},
			],
		}),
	],
});
