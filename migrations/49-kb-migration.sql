-- Django cannot do composite primary keys, so we're adding an id column
-- Very similar to migration 25

-- Adding id to tiki_freetagged_objects
ALTER TABLE tiki_freetagged_objects DROP PRIMARY KEY;

CREATE UNIQUE INDEX
    tagId_user_objectId
ON
    tiki_freetagged_objects(tagId, user, objectId);

-- This is set to AUTO_INCREMENT but it's not a primary key
-- Drop the AUTO_INCREMENT value
ALTER TABLE
    tiki_freetagged_objects
MODIFY
    tagId int(12) NOT NULL;

ALTER TABLE
    tiki_freetagged_objects
ADD
    id INT NOT NULL AUTO_INCREMENT KEY;



-- Adding id to tiki_category_objects
ALTER TABLE tiki_category_objects DROP PRIMARY KEY;

CREATE UNIQUE INDEX
    catObjectId_categId
ON
    tiki_category_objects(catObjectId, categId);

ALTER TABLE
    tiki_category_objects
ADD
    id INT NOT NULL AUTO_INCREMENT KEY;
