import { registerAdapter } from "./index";
import { workdayAdapter } from "./workday";
import { greenhouseAdapter } from "./greenhouse";
import { leverAdapter } from "./lever";
import { ashbyAdapter } from "./ashby";
import { icimsAdapter } from "./icims";
import { smartRecruitersAdapter } from "./smartrecruiters";
import { linkedinAdapter } from "./linkedin";

/** Import for side effects from the content entry to register all adapters. */
registerAdapter(workdayAdapter);
registerAdapter(greenhouseAdapter);
registerAdapter(leverAdapter);
registerAdapter(ashbyAdapter);
registerAdapter(icimsAdapter);
registerAdapter(smartRecruitersAdapter);
registerAdapter(linkedinAdapter);
