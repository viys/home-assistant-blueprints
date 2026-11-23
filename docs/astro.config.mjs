import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
  site: 'https://viys.github.io',
  base: '/home-assistant-blueprints',
  trailingSlash: 'always',
  integrations: [
    starlight({
      title: 'SONOFF Blueprints',
      description: 'Illustrated Home Assistant automation guides for SONOFF devices.',
      favicon: '/blueprint.svg',
      logo: { src: './public/blueprint.svg', alt: '', replacesTitle: false },
      customCss: ['./src/styles/custom.css'],
      components: {
        SocialIcons: './src/components/SocialLinks.astro',
        PageTitle: './src/components/BlueprintTitle.astro',
        ThemeProvider: './src/components/LightTheme.astro',
        ThemeSelect: './src/components/ThemeSelect.astro',
      },
      social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/viys/home-assistant-blueprints' }],
      editLink: { baseUrl: 'https://github.com/viys/home-assistant-blueprints/edit/dev/docs/' },
      tableOfContents: { minHeadingLevel: 2, maxHeadingLevel: 3 },
      sidebar: [
        { label: 'Choose a blueprint', slug: 'index' },
        { label: 'Start using a blueprint', slug: 'getting-started' },
        { label: 'TP-WGZBA', items: [{ autogenerate: { directory: 'blueprints/tp-wgzba' } }] },
        { label: 'TRVZB', items: [{ autogenerate: { directory: 'blueprints/trvzb' } }] },
        { label: 'TRV-ZBL', items: [{ autogenerate: { directory: 'blueprints/trv-zbl' } }] },
        { label: 'TRV-ZBT', items: [{ autogenerate: { directory: 'blueprints/trv-zbt' } }] },
        { label: 'SNZB-02DR2', items: [{ autogenerate: { directory: 'blueprints/snzb02dr2' } }] },
        { label: 'Update a blueprint', slug: 'updating' },
        { label: 'Check your automation', slug: 'checking' },
      ],
    }),
  ],
});
