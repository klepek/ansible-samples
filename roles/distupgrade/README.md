# Perform a distribution upgrade on your Fedora system

This Ansible playbook safely upgrades your Fedora system to the next
distribution release.  Here are a few noteworthy points:

* Your root ZFS dataset will be snapshotted prior to the upgrade,
  if your system has ZFS on root.
* The debug console shell will be enabled during the upgrade, so
  you can break into the machine (Ctrl+Alt+F9 after switch root)
  if the upgrade fails and leaves you with an unbootable system.
  It will then be disabled after the upgrade is complete.
* The recipe will be idempotent across failures, even if you run
  it multiple times until completion.

## Instructions

Usage:

Every time you want to upgrade your distribution, run the playbook `role-distupgrade.yml` against it.

Here is a command line example you can run (perhaps from `cron`) assuming that your host is registered and accessible via SSH at 10.25.43.24, and you are in the working directory containing `role-distupgrade.yml`:

```
ansible-playbook -v role-distupgrade.yml 10.25.43.24
```

That's all!