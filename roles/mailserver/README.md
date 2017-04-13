# Complete mail server with support for DKIM, SPF, spam classification and Sieve rules

This Ansible role deploys a full SMTP server and IMAP server, compliant
with all the best practices for spam-free and good-delivery e-mail processing,
including (but not limited to) the following features:

- DKIM
- SPF
- spam classification and reclassification
- Sieve rules
- greylisting

Consult the *Setup* section below to configure your own mail server using this
Ansible role.  Also consult the `defaults/main.yml` file to understand
the variables that influence the role's behavior.

## Operation

### Receiving mail: the pipeline

An e-mail received by your server, and meant to reach one of the accounts
you set up, traverses through this pipeline:

1. It is received by Postfix.
2. Postfix pushes it through the greylisting policy service.
   * If the policy service declines to receive it, then Postfix replies
     to the sender's server with the customary greylisting temporary failure.
2. Postfix then pushes it through the SPF verifier.
   * The SPF verifier only adds headers to the message.  It does not reject
     any e-mail at this stage.
3. Then Postfix pushes it through the DKIM signature verifier.
   * The DKIM verifier only adds headers to the message.  It does not reject
     any e-mail at this stage.
4. It is pushed through `bogofilter-dovecot-deliver`:
   * The program pipes the mail through the spam classifier (`bogofilter`),
     but only if it has never been piped through the classifier before.
   * Then the program pipes the mail through to the Dovecot LDA.
5. Dovecot LDA runs the e-mail the following Sieve scripts:
   * `/var/lib/sieve/before.d/*.sieve`, which includes the spam classifier
     ruleset that places spam into the *SPAM* folder.
   * Your own account's `~/.dovecot.sieve`, which contains the rules you
     have created using your own mail client.
   * `/var/lib/sieve/after.d/*.sieve`, which runs after your own Sieve rules.
6. Based on the decision taken by these scripts, Dovecot LDA delivers the
   e-mail to the right folder.  Should no decision be taken by these scripts,
   then the e-mail is delivered to the *INBOX* folder of your account.

### Greylisting

Your new mail server will reject any and all new e-mails from senders it hasn't
seen for 60 seconds.  This is *normal*.  The sending servers will retry after a
few minutes, after which the greylisting process will determine that the e-mail
is legitimate.

If you want to whitelist specific servers or domains for sending you e-mail
without greylisting, you can do so by adding rules to the files
`/etc/postfix/postgrey_whitelist_clients.local`.  See the documentation for
*Postgrey whitelist* online to understand what to put in that file.

### Spam handling

#### Automatic classification

Spam classification happens upon delivery, where the command
`bogofilter-dovecot-deliver` automatically runs unclassified mail through the
`bogofilter` classifier, and then pipes the result through the Dovecot LDA.

The LDA then runs the Sieve rules that inspect the headers (which contain the
result of the spam classification) and, as the first order of business, uses
the sieve rules deployed in `/var/lib/sieve/before.d` to classify the e-mails
into the *SPAM* folder if they have been deemed to be spam.

Because the rule that classifies mail as spam executes before your own Sieve
rules, all of your e-mail will go through the classifier.  This may mean that,
during the first few days, `bogofilter` will have to catch up with what *you*
understand as spam and not spam, and a few e-mails will be misclassified.
Worry not, as the process is very easy (see the next section) and `bogofilter`
learns very quickly what counts as spam and what doesn't.

**SPF and DKIM interaction with spam handling**: `bogofilter` takes into
account mail headers when deciding what is spam and what isn't, so the headers
added by the SPF and DKIM validators will inform `bogofilter` quite reliably as
to the legitimacy of the e-mail it's receiving for classification.

#### Reclassification and retraining

If the classifier has made a mistake, you can reclassify e-mails as ham or as
spam by simply using your mail client as follows:

Move them from the folder they are stored in, into the folder *Mark as spam*
(for e-mail that was wrongly classified as proper e-mail) or into the folder
*Mark as ham* (for e-mail wrongly classified as spam).

When you move mails to *Mark as spam*, the server automatically runs them
through the `bogofilter` classifier again, telling the classifer to deem those
messages as spam.  Then, the server files the e-mail into the *SPAM* folder.

When you move mails to *Mark as ham*, the server automatically runs them
through the classifier, deeming them as ham (not spam); immediately after that,
the server runs the mail through the Sieve pipeline, which usually ends up with
the mails being delivered to the *INBOX* folder (unless a rule in your own
Sieve script dictates otherwise).  Then, it marks the messages as unread
(so you can quickly spot them in their destination folder).

You'll discover quite quickly that `bogofilter` learns really well what
qualifies as spam and what does not, according to your own criteria.  It's
almost magic.  After a few days, pretty much every e-mail will be correctly
classified, with a false positive and false negative rate of less than 0.1%.

## Setup

### DKIM

For each domain that your server will send mail as, you must generate a
DKIM key pair.  Then, you must do two things:

1. Deploy the public key to the DNS server that answers queries for
   the domain.
2. Add a variable with the corresponding private key to your Ansible
   setup that will run this role.

#### Key generation

Suppose in your Ansible node you create folder `secrets/dkim`, relative
to your playbook that includes this role.

Change into that directory.  Then, for each domain, run the following script:

```bash
DOMAIN=<type your domain here>
mkdir $DOMAIN
opendkim-genkey -D $DOMAIN -d $DOMAIN -s default -b 2048
```

That process will create the necessary key pairs.
Note that you will have to have the program `opendkim-genkey`
installed on the Ansible master node, which is available
within the opendkim package.

Now you can confirm that the necessary keys are in `secrets/dkim/$DOMAIN`.
The file `default.private` contains the private key.  The file `default.txt`
contains the public key, in BIND record format.

#### Setup of public key in DNS server

For each domain, update its DNS server to include the record stored in
`secrets/dkim/$DOMAIN/default.txt`.  If you are running BIND, it's just
a one-line addition to the respective zone file.  The important goal is
to publish the contents of the `private.txt` file (in each key
subdirectory) via DNS, following the DNS portion of the guide here:
https://support.dnsimple.com/articles/dkim-record/ .
Failure to do so will cause other mail servers to mark your outgoing e-mails
from these domains as not authentic (improperly signed by DKIM).

#### Setup of private key in role configuration

Now register the private keys as a var in your playbook or vars file:

```yaml
dkim:
  domain1.com: '{{ lookup("file", "secrets/dkim/domain1/default.private") }}'
  domain2.com: '{{ lookup("file", "secrets/dkim/domain1/default.private") }}'
#...and so on and so forth...
```