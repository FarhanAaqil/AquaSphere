// Results of the synthetic-input audit (scripts/build_web_data.py -> web/data/input_audit.json).
// Views built on a table whose satellite columns were proven synthetic must say so.

import { results } from './api.js';

const ABLATION_TABLE = 'tests/fixtures/argo_200.parquet';
const LABEL = { sat_sst: 'satellite SST', sss: 'SSS', sla: 'SLA', ug: 'currents', vg: 'currents', u10: 'wind', v10: 'wind' };

/** Synthetic channels in the table behind ablation.json, or [] if none were found or no audit exists. */
export async function ablationSyntheticChannels() {
  try {
    const audit = await results('input_audit');
    const t = audit.tables.find((x) => x.table === ABLATION_TABLE);
    return t?.status === 'synthetic_found' ? t.synthetic_channels : [];
  } catch {
    return [];
  }
}

/** "SSS, SLA, currents and wind" from a channel list. */
export function describeChannels(channels) {
  const names = [...new Set(channels.filter((c) => c !== 'sat_sst').map((c) => LABEL[c] || c))];
  if (names.length <= 1) return names.join('');
  return `${names.slice(0, -1).join(', ')} and ${names.at(-1)}`;
}
