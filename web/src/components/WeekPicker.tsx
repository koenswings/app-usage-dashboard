import { For } from 'solid-js';
import { formatWeekLabel, fridayOf, shiftWeek } from '../lib/week';

interface WeekPickerProps {
  week: string;
  weeks: string[];
  onChange: (week: string) => void;
}

export function WeekPicker(props: WeekPickerProps) {
  const weekIds = () => {
    const extra = props.weeks.includes(props.week) ? props.weeks : [props.week, ...props.weeks];
    return extra;
  };

  return (
    <div class="week-picker" data-testid="week-picker">
      <button type="button" onClick={() => props.onChange(shiftWeek(props.week, -1))} aria-label="Previous week">
        Previous week
      </button>
      <select
        aria-label="School week"
        value={props.week}
        onChange={(event) => props.onChange(event.currentTarget.value)}
      >
        <For each={weekIds()}>
          {(id) => <option value={id}>{formatWeekLabel(id, fridayOf(id))}</option>}
        </For>
      </select>
      <button type="button" onClick={() => props.onChange(shiftWeek(props.week, 1))} aria-label="Next week">
        Next week
      </button>
    </div>
  );
}
