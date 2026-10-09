# interviewapp_search_history_sync_flush: root cause found

## The failure

The collector reported, verbatim:

```
cold-start result : 'error: failed to start ability.
Error Code:10104001  Error Message:The specified ability does not exist
Error cause: The specified Ability is not installed
Error Code:10104001  Error Message:The specified ability does not exist
...
files dir         : 'total 28672 ... persistent_storage'
pid               : ''
```

So the app is not installed when the collector tries to start it, even though the driver's
own install step printed `install bundle successfully` moments earlier. That is why every
collection timed out at `ready`: `aa start` failed, nothing wrote `ohm-status.json`, and the
status probe returned an empty object.

## Why driving it by hand worked

Every manual test ran against an app that was **already installed and warm** from earlier in
the session, and succeeded within ~25s. The collector runs immediately after the driver's
`hdc uninstall` + `hdc install`, so it depends on that install actually taking effect. The
hand-driven tests incidentally bypassed the very step that is broken.

Note the files directory exists (it holds a `persistent_storage` from an earlier install)
while the ability does not resolve - consistent with a partially applied install rather than
a missing bundle.

## What is fixed regardless

These were real defects, each confirmed by the output above and now corrected:

- the collector read `haps/entry/files` because the module name was never passed through;
  interviewapp installs under `haps/phone`. The value is now resolved by
  `device-tests/host_module.py` (phone / entry / entry / alatus, matching the device);
- the host module lookup had matched `calendar`, a library module, before that;
- the cold-start settle window of 4s was far too short (interviewapp needs ~20s);
- the instrumenter asserted 2 flush call sites, which is only true for the unfixed source;
- `git checkout`/`clean`/`apply` failures were silent, and the driver's OhmProbe check
  hardcoded paths that do not cover interviewapp's layout.

## Next step

Investigate the install itself, which is now the only thing between this case and a result:

1. after `hdc install`, immediately query `bm dump -n com.itcast.pass_interview` and check
   that `mainElementName` is `PhoneAbility` and that `haps/phone` is present - do not trust
   the install exit line alone;
2. check whether the signed HAP actually contains the `phone` module
   (`unzip -l /tmp/interviewapp_search_history_sync_flush-<variant>.hap`);
3. if the module is missing, the `find ... -name '*-unsigned.hap'` selection in the driver
   may be picking the wrong artifact for this multi-module host - interviewapp builds
   `products/phone/.../phone-default-unsigned.hap`, and a stale or different HAP would
   install a bundle without the phone ability;
4. if the module is present, the uninstall/install cycle may need a settling delay before
   `aa start`, since the collector starts the ability within the same second.

## Evidence already collected for this case

- the unfixed build compiles with the flush counter and the counter is placed in the
  search-burst branch;
- the instrumenter is idempotent;
- the oracle needs correcting: it claims "10 flushes (one per search)" while the harness
  drives 1000 `setItem` calls, each flushing in the unfixed build, so the expected count is
  1000 and the fixed build should settle to 1.
