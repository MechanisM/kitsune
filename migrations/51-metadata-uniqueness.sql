ALTER TABLE `wiki_firefoxversion`
    ADD UNIQUE (`item_id`, `document_id`);
ALTER TABLE `wiki_operatingsystem`
    ADD UNIQUE (`item_id`, `document_id`);
