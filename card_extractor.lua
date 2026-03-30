local CardExtractor = {}

function CardExtractor.get_details(card)
    if not card then return {} end
    return {
        name = (card.ability and card.ability.name) or (card.config and card.config.center and card.config.center.name) or "unknown",
        id_key = (card.config and card.config.center and card.config.center.key) or "unknown",
        suit = (card.base and card.base.suit) or "none",
        value = (card.base and card.base.value) or "none",
        edition = (card.edition and card.edition.type) or "standard",
        enhancement = (card.config and card.config.center and card.config.center.name ~= card.base.name and card.config.center.name) or "none",
        cost = card.cost or 0,           -- 商店购买价格
        sell_cost = card.sell_cost or 0  -- 售卖价格
    }
end

return CardExtractor