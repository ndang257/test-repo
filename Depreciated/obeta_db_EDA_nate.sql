-- Look at product_ids with negative pick_volume
SELECT product_id 
FROM pick_data 
WHERE pick_volume = (SELECT pick_volume < 0);

-- Look at how many records have negative pick_volume
SELECT COUNT(pick_volume) FROM pick_data WHERE pick_volume < 0;

SELECT * FROM product_data 
WHERE 
product_id = (SELECT product_id FROM pick_data 
WHERE pick_volume = (SELECT pick_volume = -1);

