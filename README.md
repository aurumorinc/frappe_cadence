### Frappe Cadence

Open-Source Cold Outreach & Sales Engagement Automation

Frappe Cadence is a powerful email automation tool built on the Frappe Framework, designed to replace expensive SaaS subscriptions like Apollo.io, Lemlist, or Instantly.ai. It allows sales teams and marketers to create multi-step email drip cadences, automate follow-ups, and track lead engagement directly within their self-hosted ecosystem.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch main
bench install-app frappe_cadence
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/frappe_cadence
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
