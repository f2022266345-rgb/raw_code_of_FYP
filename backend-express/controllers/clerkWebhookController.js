import { Webhook } from "svix";
import User from "../model/Users.js";

// Handle Clerk webhook events
export const handleClerkWebhook = async (req, res) => {
  const CLERK_WEBHOOK_SECRET = process.env.CLERK_WEBHOOK_SECRET;

  if (!CLERK_WEBHOOK_SECRET) {
    return res.status(500).json({ error: "CLERK_WEBHOOK_SECRET is not configured" });
  }

  // Get headers for signature verification
  const svixHeaders = {
    "svix-id": req.headers["svix-id"],
    "svix-timestamp": req.headers["svix-timestamp"],
    "svix-signature": req.headers["svix-signature"],
  };

  let evt;

  try {
    // Verify webhook signature
    const wh = new Webhook(CLERK_WEBHOOK_SECRET);
    evt = wh.verify(JSON.stringify(req.body), svixHeaders);
  } catch (error) {
    console.error("Webhook signature verification failed:", error.message);
    return res.status(400).json({
      error: "Webhook signature verification failed",
      message: error.message,
    });
  }

  try {
    const eventType = evt.type;

    if (eventType === "user.created") {
      // Handle user creation event
      const { id, email_addresses, first_name, last_name } = evt.data;
      const clerkId = id;
      const email = email_addresses[0]?.email_address;
      const fullName = `${first_name || ""} ${last_name || ""}`.trim() || email;

      if (!email) {
        return res.status(400).json({ error: "Email address not provided" });
      }

      // Check if user already exists
      const existingUser = await User.findOne({ where: { clerkId } });
      if (existingUser) {
        console.log(`User with clerkId ${clerkId} already exists`);
        return res.status(200).json({ message: "User already exists" });
      }

      // Create user in database
      const newUser = await User.create({
        clerkId,
        email,
        fullName,
      });

      console.log(`User created successfully: ${newUser.id}`);
      return res.status(201).json({
        success: true,
        message: "User provisioned successfully",
        userId: newUser.id,
      });
    } else if (eventType === "user.updated") {
      // Handle user update event
      const { id, email_addresses, first_name, last_name } = evt.data;
      const clerkId = id;
      const email = email_addresses[0]?.email_address;
      const fullName = `${first_name || ""} ${last_name || ""}`.trim();

      if (!email) {
        return res.status(400).json({ error: "Email address not provided" });
      }

      // Update user in database
      const [updatedCount] = await User.update(
        { email, fullName },
        { where: { clerkId } }
      );

      if (updatedCount === 0) {
        console.warn(`User with clerkId ${clerkId} not found for update`);
        return res.status(404).json({ error: "User not found" });
      }

      console.log(`User updated successfully: ${clerkId}`);
      return res.status(200).json({
        success: true,
        message: "User updated successfully",
      });
    } else if (eventType === "user.deleted") {
      // Handle user deletion event
      const { id } = evt.data;
      const clerkId = id;

      const deletedCount = await User.destroy({ where: { clerkId } });

      if (deletedCount === 0) {
        console.warn(`User with clerkId ${clerkId} not found for deletion`);
        return res.status(404).json({ error: "User not found" });
      }

      console.log(`User deleted successfully: ${clerkId}`);
      return res.status(200).json({
        success: true,
        message: "User deleted successfully",
      });
    } else {
      // Handle other event types
      console.log(`Unhandled event type: ${eventType}`);
      return res.status(200).json({ success: true, message: "Event received" });
    }
  } catch (error) {
    console.error("Webhook processing error:", error);
    return res.status(500).json({
      error: "Webhook processing failed",
      message: error.message,
    });
  }
};

export default { handleClerkWebhook };
