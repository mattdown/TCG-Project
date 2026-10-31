"""Art direction for card art prompts (docs/theme.md, "Art direction").

A prompt is a scene written for the card (scenes.json) plus STYLE, which every card shares.
The species looks, job props and habitat settings below go into the briefs that scenes are
written from, so a new species, job or aspect needs an entry here, but a new card never does.
"""

STYLE = ("Highly rendered 3D animated feature-film style, like a modern Disney/Pixar movie: soft subsurface "
         "scattering on the cap, velvety gills, warm rim lighting, shallow depth of field. Centred composition, "
         "vertical 4:5 framing, background a soft radial glow in {glow} fading to dark navy at the edges. "
         "Every character is a mushroom with a cap and a stalk body: no humans. No text, no frame.")

SPECIES = {
    "Fly-agaric": "a bright red domed cap with white spots and a white stalk with a frilly ring",
    "Chanterelle": "a golden-orange funnel-shaped cap with wavy edges and soft ridges underneath",
    "Morel": "a tall, conical, honeycombed tan-brown cap full of little pits",
    "Porcini": "a plump body, a glossy chestnut-brown bun-shaped cap and a thick pale stalk",
    "Oyster": "a fan-shaped, off-centre, pale grey-blue cap with velvety gills",
    "Inkcap": "a tall, shaggy white bell-shaped cap whose edges drip with black ink",
    "Puffball": "a round, chubby white ball of a body with a fine pebbly texture and no cap rim",
    "Enoki": "a very tall, thin creamy-white stalk topped by a tiny round cap",
    "Shiitake": "a wide brown cap flecked with pale cracks and a curled-under rim",
    "Truffle": "a small, lumpy, knobbly dark brown-black round body and a gruff face",
    "Button": "a tiny, smooth, round white button cap and a youthful face",
    "Portobello": "a big, wide, flat dark-brown cap with chocolate gills and broad shoulders",
    "Lion's-mane": "a shaggy white cascade of soft icicle-like spines, like a fluffy mane",
    "Turkey-tail": "a ruffled fan-shaped cap striped in bands of brown, tan and rust",
    "Honey": "a honey-gold cap with fine dark scales and a slim stalk with a ring",
    "Ghost": "a pale, translucent green-white cap that glows softly from within",
    "Snowcap": "a pure white frosted cap dusted with snow crystals and pale blue undertones",
    "Waxcap": "a glossy, waxy, bright scarlet-orange conical cap",
}

JOBS = {
    "Fisher": "a fisher with a twig fishing rod, a dewdrop bobber and a little rain hat",
    "Baker": "a baker in a flour-dusted apron, holding a loaf of seed bread",
    "Knight": "a knight with an acorn-cap helmet, a walnut-shell shield and a thorn sword",
    "Archer": "an archer with a bent-twig bow and pine-needle arrows in a bark quiver",
    "Forager": "a forager with a woven grass basket of berries and seeds and a walking stick",
    "Bard": "a bard playing a lute made from half a chestnut shell, with a feather in its cap",
    "Postman": "a postman in a peaked cap with a satchel of folded leaf letters",
    "Gardener": "a gardener in a straw hat with a thimble watering can and a tiny trowel",
    "Lamplighter": "a lamplighter carrying a firefly lantern on a long reed pole",
    "Burglar": "a sneaky burglar in a striped mask with a sack holding a stolen acorn",
    "Doctor": "a doctor with a dewdrop head mirror, a leaf bandage roll and a little bag",
    "Blacksmith": "a blacksmith in a leather apron with a pebble hammer at a glowing ember anvil",
    "Scholar": "a scholar with round spectacles and a stack of leaf books or a scroll",
    "Miner": "a miner in a helmet with a glow-worm headlamp, carrying a thorn pickaxe",
    "Sailor": "a sailor in a sailor's cap with a coil of spider-silk rope and a walnut-shell boat",
    "Chef": "a chef in a tall toque with a wooden spoon and an acorn-cup pot",
    "Firefighter": "a firefighter in a red berry-cup helmet spraying dewdrops from a hollow grass-stem hose",
    "Beekeeper": "a beekeeper in a veiled hat with a friendly bumblebee and a honey drop",
    "Tailor": "a tailor with a grass measuring tape, a thimble and a thistle needle and thread",
    "Explorer": "an explorer in an acorn-cap pith helmet with a leaf map and a hollow-twig spyglass",
}

# aspect id → (setting, glow colour); "" is a neutral card.
HABITATS = {
    "aspect_1": ("a burnt woodland floor with ash, charcoal twigs and drifting embers", "warm ember red-orange"),
    "aspect_2": ("the edge of a rain puddle with lily pads, reeds and raindrops", "deep teal blue"),
    "aspect_3": ("the deep forest floor with moss cushions, ferns and a fallen log", "rich moss green"),
    "aspect_4": ("a sunny meadow with wildflowers, clover and wheat stalks", "warm golden yellow"),
    "aspect_5": ("a forest at night with fireflies, moonlight and glowing mushrooms", "soft violet purple"),
    "aspect_6": ("snowy winter woods with frost, pine needles and icicles", "icy cyan"),
    "": ("any cosy woodland spot (a neutral card)", "soft slate blue-grey"),
}
