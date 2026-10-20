"""Theme data for generated cards: mushroom species and jobs (see docs/theme.md)."""

JOBS = ("Fisher", "Baker", "Knight", "Archer", "Forager", "Bard", "Postman", "Gardener", "Lamplighter", "Burglar",
        "Doctor", "Blacksmith", "Scholar", "Miner", "Sailor", "Chef", "Firefighter", "Beekeeper", "Tailor", "Explorer")

SPECIES = ("Fly-agaric", "Chanterelle", "Morel", "Porcini", "Oyster", "Inkcap", "Puffball", "Enoki", "Shiitake",
           "Truffle", "Button", "Portobello", "Lion's-mane", "Turkey-tail", "Honey", "Ghost", "Snowcap", "Waxcap")

# Subtitles tell apart versions of the same species + job ("Porcini Baker – Up Before Dawn").
# They're picked from what the card does, so the name hints at the ability. Theme data only:
# no rule depends on them.
SUBTITLES_BY_TRIGGER = {
    "on_play": ("Fresh Out of the Ground", "First Day on the Job", "Just Sprouted", "Fashionably Early",
                "Grand Entrance", "Reporting for Duty", "Here to Help", "New in Town", "Straight from the Spore",
                "Turning Up", "Off the Boat", "Hot off the Cart"),
    "on_score": ("Employee of the Month", "Worth Every Coin", "Crowd Favourite", "Top of the Class",
                 "Paid in Full", "Prize Winner", "Local Legend", "Ribbon Collector", "Making a Name",
                 "On the Podium", "Ahead of Quota", "Golden Gills"),
    "on_attack": ("First into the Fray", "Charging Ahead", "Picking a Fight", "No Time to Wait", "Spoiling for Trouble",
                  "Head First", "Leading the Charge", "Rolling Up Sleeves", "Never Backs Down", "Brave to a Fault"),
    "on_defeated": ("Last Act", "Going Out in Style", "Leaves Something Behind", "One Final Favour",
                    "Spores on the Wind", "Not Forgotten", "Back to the Soil", "Parting Gift", "Last Batch",
                    "Famous Last Words"),
    "start_of_turn": ("Up Before Dawn", "Early Riser", "Morning Rounds", "First Light", "Rise and Shine",
                      "Dew Collector", "Opening Shift", "Clocking In", "Sunrise Watch", "Bright and Early"),
    "end_of_turn": ("Night Shift", "Working Late", "Last to Leave", "Lights Out", "Burning the Midnight Oil",
                    "Closing Time", "Twilight Watch", "After Hours", "Moonlit Rounds", "Clocking Off"),
    "another_played": ("Team Player", "Brings Friends", "Rallying the Crew", "Proud Mentor", "Guild Leader",
                       "Never Works Alone", "Family Business", "Making Introductions", "Union Rep",
                       "Head of the Table"),
    "opposing_defeated": ("Sore Winner", "Keeps Score", "Taking Notes", "Picks Up the Pieces", "Bounty Hunter",
                          "Waiting in the Wings", "Opportunist", "Silver Lining", "Victory Lap", "Tallying Up"),
}
SUBTITLES_BY_EFFECT = {
    "deal_damage": ("Sharp Tongue", "Heavy Handed", "Prickly Customer", "Thorn in the Side", "Hard Knocks",
                    "Short Fuse", "Bramble Brawler", "Pointy End", "Spiky Temper", "Rough and Tumble"),
    "remove_damage": ("Gentle Touch", "Patches Things Up", "Kind Hands", "Soothing Spores", "House Calls",
                      "Bandage Bundle", "Warm Broth", "Good as New", "Steady Hands", "Mends and Minds"),
    "defeat": ("Final Word", "No Second Chances", "Dreaded Visitor", "Closing the Case", "Clean Sweep",
               "Grim Gardener", "Uproots Trouble", "Weed Puller", "Last Call", "End of the Road"),
    "return_to_hand": ("Sends You Packing", "Return to Sender", "Shows the Door", "Back to Square One",
                       "Polite but Firm", "Not Today", "Out You Go", "Wrong Address", "Rewinding", "Do Over"),
    "exhaust": ("Long Lecture", "Sleepy Spores", "Tires You Out", "Lullaby Hum", "Yawn Spreader",
                "Slow Talker", "Puts Feet Up", "Afternoon Nap", "Heavy Eyelids", "Endless Paperwork"),
    "ready": ("Second Wind", "Pep Talk", "Fresh Pot of Tea", "Wake-Up Call", "Back on Your Feet",
              "Rallying Cry", "Morning Whistle", "Spring in the Step", "Strong Coffee", "Encore"),
    "cant_ready": ("Sticky Situation", "Tangled Up", "Stuck in the Mud", "Knotted Laces", "Overslept",
                   "Glued to the Spot", "Snowed In", "Lost the Key", "Web Spinner", "Molasses Trap"),
    "modify_stat": ("Pumped Up", "Growth Spurt", "Big Day", "Puffed Up", "Showing Off", "Second Helping",
                    "Stretching Out", "Heads Up", "Flexing", "On a Roll"),
    "grant_keyword": ("Watchful Friend", "Lends a Hand", "Shield Bearer", "Good Advice", "Training Day",
                      "Hand-Me-Downs", "Safety First", "Buddy System", "Trusty Kit", "Handy Tips"),
    "draw": ("Bookworm", "Avid Reader", "Letter Opener", "Full Satchel", "Knows a Thing", "Rumour Mill",
             "Curious Cap", "Note Taker", "Map Maker", "Loose Pages"),
    "discard": ("Pickpocket", "Light Fingers", "Butterfingers", "Distraction", "Spills the Beans",
                "Rummages Through", "Lost Property", "Sneaky Swipe", "Paper Shredder", "Gossip"),
    "gain_vp": ("Rising Star", "Crown Polisher", "Medal Count", "Blue Ribbon", "Fan Favourite", "Big Break",
                "Making Headlines", "Award Season", "Toast of the Town", "Hall of Fame"),
    "lose_vp": ("Spoilsport", "Rains on Parades", "Heckler", "Party Pooper", "Sour Grapes", "Tough Critic",
                "Bad Review", "Wet Blanket", "Rival", "Grumbler"),
    "add_energy": ("Green Thumb", "Deep Roots", "Compost Keeper", "Rich Soil", "Seed Saver", "Mulch Master",
                   "Rainmaker", "Planting Season", "Root Network", "Harvest Moon"),
}
SUBTITLES_BY_STATIC = {
    "self_situational": ("Bigger Than Looks", "Stands Tall", "Rises to the Occasion", "Steady Under Pressure",
                         "Fights Dirty", "Stubborn Streak", "Thick Stalk", "Hard Cap", "Mean Streak", "Unflappable"),
    "lord": ("Head of the Guild", "Proud Teacher", "Shift Supervisor", "Captain of the Crew", "Workshop Owner",
             "Grand Master", "Inspiring Boss", "Old Hand", "Foreman", "Union Leader"),
    "self_keyword": ("Hard to Pin Down", "Thick Skin", "Knows the Ropes", "Quick on the Draw", "Second Nature",
                     "Seasoned Pro", "Battle Scarred", "Old Habits", "Instinct", "Light on Feet"),
    "discount": ("Friends and Family Rate", "Bulk Buyer", "Knows a Guy", "Coupon Clipper", "Haggler",
                 "Trade Discount", "Mates' Rates", "Bargain Hunter", "Two for One", "Shop Keeper"),
    "debuff": ("Rubs Salt In", "Kicks When Down", "Jeering Crowd", "Unkind Words", "Lingering Gloom",
               "Pours Cold Water", "Doom and Gloom", "Grim Reminder", "Stormcloud", "Dampener"),
}
SUBTITLES_GENERIC = ("Apprentice", "Old Timer", "Weekend Helper", "Part-Timer", "Rookie", "Veteran",
                     "Village Favourite", "Wanderer", "Daydreamer", "Night Owl", "Odd Job", "Second Cousin",
                     "Trainee", "Retired (Mostly)", "Volunteer", "Understudy")

# Action card names: an aspect word plus a noun for what the action does ("Ember Volley").
ACTION_WORDS = {
    "aspect_1": ("Ember", "Cinder", "Smoulder", "Bonfire"),
    "aspect_2": ("Bog", "Murk", "Mire", "Marsh"),
    "aspect_3": ("Moss", "Fern", "Root", "Lichen"),
    "aspect_4": ("Meadow", "Clover", "Buttercup", "Hayfield"),
    "aspect_5": ("Glow", "Lantern", "Starlit", "Firefly"),
    "aspect_6": ("Frost", "Rime", "Snowdrift", "Icicle"),
}
ACTION_NOUNS = {
    "deal_damage": ("Volley", "Ambush", "Sting", "Pummel", "Barrage", "Thump", "Pelting"),
    "remove_damage": ("Remedy", "Poultice", "Tonic", "Mending", "Salve", "Tea Break"),
    "defeat": ("Reckoning", "Downfall", "Uprooting", "Eviction", "Collapse"),
    "return_to_hand": ("Gust", "Recall", "Rewind", "Detour", "Homecoming"),
    "exhaust": ("Lullaby", "Slumber", "Drowsiness", "Haze", "Torpor"),
    "ready": ("Reveille", "Rally", "Second Wind", "Wake-Up", "Bugle Call"),
    "cant_ready": ("Snare", "Tangle", "Quagmire", "Bind", "Lockdown"),
    "modify_stat": ("Surge", "Bloom", "Flourish", "Swell", "Wither", "Boost"),
    "grant_keyword": ("Blessing", "Drill", "Training", "Ward", "Lesson"),
    "draw": ("Gossip", "Insight", "Almanac", "Scouting", "Letters", "Forecast"),
    "discard": ("Pilfering", "Distraction", "Scatter", "Mischief", "Fumble"),
    "gain_vp": ("Festival", "Parade", "Triumph", "Fanfare", "Harvest Fair"),
    "lose_vp": ("Scandal", "Rumours", "Mockery", "Spoiled Feast", "Rotten Luck"),
    "add_energy": ("Harvest", "Sowing", "Spring Rain", "Compost", "Planting"),
}
