# Changelog

## [0.7.0](https://github.com/cpujades/fathom/compare/v0.6.0...v0.7.0) (2026-01-28)


### Features

* add api metadata and improve logging ([#50](https://github.com/cpujades/fathom/issues/50)) ([ef07228](https://github.com/cpujades/fathom/commit/ef072287bb2490fc5fb0315d863209bcb02f4da5))

## [0.6.0](https://github.com/cpujades/fathom/compare/v0.5.1...v0.6.0) (2026-01-27)


### Features

* **cache:** reuse cached summaries securely via jobs-based RLS ([#49](https://github.com/cpujades/fathom/issues/49)) ([037a8e0](https://github.com/cpujades/fathom/commit/037a8e02c162f083ec402026232a622f1f25be67))


### Bug Fixes

* **pipeline:** make transcript/summary inserts idempotent ([#47](https://github.com/cpujades/fathom/issues/47)) ([1b5754c](https://github.com/cpujades/fathom/commit/1b5754c525e94a00071c7634af58c25f08f5416b))

## [0.5.1](https://github.com/cpujades/fathom/compare/v0.5.0...v0.5.1) (2026-01-27)


### Refactoring

* **structure:** move entrypoint to api app and group orchestration ([#45](https://github.com/cpujades/fathom/issues/45)) ([8f76eed](https://github.com/cpujades/fathom/commit/8f76eedbec6a99de6ad93026a02ce93471152ac7))

## [0.5.0](https://github.com/cpujades/fathom/compare/v0.4.0...v0.5.0) (2026-01-27)


### Features

* **best-practices:** add request guardrails, CORS allowlist, and basic rate limiting ([#36](https://github.com/cpujades/fathom/issues/36)) ([49c373f](https://github.com/cpujades/fathom/commit/49c373fd35b738a94684bfc32a63deda16d8f73d))
* **pdf:** generate PDFs on demand and keep summaries markdown-first ([#38](https://github.com/cpujades/fathom/issues/38)) ([3c01b23](https://github.com/cpujades/fathom/commit/3c01b232cd7457e2a070200373ef565defe2a6b1))
* **transcription:** add async Deepgram flow with URL fallback ([#37](https://github.com/cpujades/fathom/issues/37)) ([2f117e4](https://github.com/cpujades/fathom/commit/2f117e460e4da15fae2ae2a1337eddcd27de1665))
* **worker:** add async job processing pipeline with retries ([#34](https://github.com/cpujades/fathom/issues/34)) ([403ef6d](https://github.com/cpujades/fathom/commit/403ef6ded131e04cc76b06e93beacb221bdf5bad))


### Refactoring

* **app:** add app factory ([#42](https://github.com/cpujades/fathom/issues/42)) ([0b4f6b3](https://github.com/cpujades/fathom/commit/0b4f6b3fdfb6169bcad87980405066b235480f14))
* **config:** simplify settings by moving constants to modules ([#40](https://github.com/cpujades/fathom/issues/40)) ([e0eade7](https://github.com/cpujades/fathom/commit/e0eade74a1435697ed6c616881ec1799d3e0a4b1))
* narrow exception handling and extract helpers ([#39](https://github.com/cpujades/fathom/issues/39)) ([002a963](https://github.com/cpujades/fathom/commit/002a963524403537eea3e91d8a29a80fb1af3609))
* **summarizer:** use AsyncOpenAI and await summaries ([#41](https://github.com/cpujades/fathom/issues/41)) ([439352e](https://github.com/cpujades/fathom/commit/439352e20af92c9b649896a140eebc91b1ebb90e))


### Chores

* **deps:** bump weasyprint in the uv group across 1 directory ([#33](https://github.com/cpujades/fathom/issues/33)) ([b5f44fa](https://github.com/cpujades/fathom/commit/b5f44fa654bdd45134464d1d8ad2acd7365f1ed8))
* **dev:** add lifespan hook to run embedded worker locally ([#44](https://github.com/cpujades/fathom/issues/44)) ([50b6019](https://github.com/cpujades/fathom/commit/50b6019e30be3d9548461e13359b7dce20753836))
* **logging:** add context-aware global config and debug-friendly settings ([#43](https://github.com/cpujades/fathom/issues/43)) ([85cec13](https://github.com/cpujades/fathom/commit/85cec1326c4bc7f9f925ef067eed37f1b3206992))

## [0.4.0](https://github.com/cpujades/fathom/compare/v0.3.3...v0.4.0) (2026-01-18)


### Features

* **security:** tighten RLS and storage access ([#32](https://github.com/cpujades/fathom/issues/32)) ([159bb4d](https://github.com/cpujades/fathom/commit/159bb4d0bcd426dffd1c29f93a574f2cebbe1315))


### Refactoring

* **application:** move endpoint orchestration out of routers ([#28](https://github.com/cpujades/fathom/issues/28)) ([8cc843b](https://github.com/cpujades/fathom/commit/8cc843b9f9894dd267b6e9b06d0617455bd573b9))
* **async:** use async Supabase client and endpoints ([#27](https://github.com/cpujades/fathom/issues/27)) ([dd76df2](https://github.com/cpujades/fathom/commit/dd76df26da43bc181c883d6083f445f352a9af0a))
* **crud:** split Supabase CRUD and helpers ([#29](https://github.com/cpujades/fathom/issues/29)) ([82fdd9a](https://github.com/cpujades/fathom/commit/82fdd9a6bf3bf021198b33728ad60d47087ef462))
* **settings:** adopt pydantic-settings with cached DI ([#26](https://github.com/cpujades/fathom/issues/26)) ([1830038](https://github.com/cpujades/fathom/commit/1830038badda72cb69cb20383ca1a253a640dc88))


### Chores

* **deps:** bump filelock in the uv group across 1 directory ([#31](https://github.com/cpujades/fathom/issues/31)) ([c246747](https://github.com/cpujades/fathom/commit/c246747d3da724cf1f6c34c346bba185bf8c4664))
* **deps:** bump virtualenv in the uv group across 1 directory ([#25](https://github.com/cpujades/fathom/issues/25)) ([5d0a4fd](https://github.com/cpujades/fathom/commit/5d0a4fdf3ee794ff01c4a681a39b714e56f1cc95))

## [0.3.3](https://github.com/cpujades/fathom/compare/v0.3.2...v0.3.3) (2026-01-10)


### CI

* **actions:** set explicit workflow token permissions ([#23](https://github.com/cpujades/fathom/issues/23)) ([4a2f348](https://github.com/cpujades/fathom/commit/4a2f34835773cf8a3150def02235b628749da4e2))

## [0.3.2](https://github.com/cpujades/fathom/compare/v0.3.1...v0.3.2) (2026-01-10)


### CI

* **security:** consolidate CodeQL scan into a single configuration ([#21](https://github.com/cpujades/fathom/issues/21)) ([61b1c84](https://github.com/cpujades/fathom/commit/61b1c847a8e3c70cbf4495d1ff0dfbfd992c571b))


### Chores

* **deps:** bump the github-actions group with 4 updates ([#20](https://github.com/cpujades/fathom/issues/20)) ([4526d56](https://github.com/cpujades/fathom/commit/4526d56b930078a2d2e212e5cda709de87721cdf))

## [0.3.1](https://github.com/cpujades/fathom/compare/v0.3.0...v0.3.1) (2026-01-10)


### CI

* **actions:** modernize CodeQL scanning and enable Dependabot for actions ([#18](https://github.com/cpujades/fathom/issues/18)) ([b923b08](https://github.com/cpujades/fathom/commit/b923b08e766c521135b4e953b74f15bd1e0786a8))

## [0.3.0](https://github.com/cpujades/fathom/compare/v0.2.2...v0.3.0) (2026-01-10)


### Features

* **api:** add endpoints, supabase service, and custom errors ([2ee769d](https://github.com/cpujades/fathom/commit/2ee769dff9d535e30b8bb7c726aa04b56c06b3f1))


### CI

* enforce Conventional Commit PR titles ([#17](https://github.com/cpujades/fathom/issues/17)) ([13fde73](https://github.com/cpujades/fathom/commit/13fde7352857c6419ac624d9bff3ee6777702d97))

## [0.2.2](https://github.com/cpujades/fathom/compare/v0.2.1...v0.2.2) (2026-01-09)


### CI

* **release:** customize release-please version bumping and harden supabase deploy workflows ([#10](https://github.com/cpujades/fathom/issues/10)) ([0cba58a](https://github.com/cpujades/fathom/commit/0cba58a9a4ad17339e8d9f80c09b44ceb24c81e2))
* **supabase:** add PR checks and staging/prod migration deploy workflows ([#9](https://github.com/cpujades/fathom/issues/9)) ([52ef420](https://github.com/cpujades/fathom/commit/52ef42058fa89c7e7bb73ad827ca28e5138659c2))
* **supabase:** always report PR check status and skip when unchanged ([#12](https://github.com/cpujades/fathom/issues/12)) ([b973d02](https://github.com/cpujades/fathom/commit/b973d02e8ad4292d7bc5d5cc8ee8306e5273bfe5))

## [0.2.1](https://github.com/cpujades/fathom/compare/v0.2.0...v0.2.1) (2026-01-07)


### Bug Fixes

* **release:** move include-component-in-tag to package config ([#8](https://github.com/cpujades/fathom/issues/8)) ([18eb18a](https://github.com/cpujades/fathom/commit/18eb18ac5241db6294f7f890da5098848764eaa6))

## [0.2.0](https://github.com/cpujades/fathom/compare/fathom-v0.1.0...fathom-v0.2.0) (2026-01-05)


### Features

* **api:** initial MVP ([#1](https://github.com/cpujades/fathom/issues/1)) ([11f104c](https://github.com/cpujades/fathom/commit/11f104cec596f99f5e3615abedc4e4c0ce388554))


### Bug Fixes

* **ci:** use PAT token for release-please to trigger checks ([#3](https://github.com/cpujades/fathom/issues/3)) ([a7c17aa](https://github.com/cpujades/fathom/commit/a7c17aa83aeb354aa2d7cb2e14ee98900aad08fe))

## Changelog

All notable changes to this project will be documented in this file.
