export const UPLINK_NOT_MEASURED_MESSAGE =
  "Reachability isn't measured yet: the dashboard's network link isn't connected.";

/** measured is optional on older collectors; only an explicit false is "not measured". */
export function uplinkNotMeasured(measured: boolean | undefined): boolean {
  return measured === false;
}
