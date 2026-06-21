import { registerAdapter } from "./index";
import { workdayAdapter } from "./workday";

/** Import for side effects from the content entry to register all adapters. */
registerAdapter(workdayAdapter);
